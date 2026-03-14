import asyncio
import json
import logging
from typing import Dict, Set, Optional, Any, List
from datetime import datetime
from fastapi import WebSocket
from ..core.config import settings
from ..core.security import SecurityUtils
from ..core.database import supabase

logger = logging.getLogger(__name__)

class ConnectionManager:
    """
    Manages WebSocket connections for real-time features
    Uses Supabase Realtime instead of Redis
    """
    
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}
        self.online_users: Set[str] = set()
        self.typing_status: Dict[str, Set[str]] = {}
        self.cleanup_task = None
        self.realtime_channels = {}  # Store Supabase Realtime channels
    
    async def initialize(self):
        """Initialize and start background tasks"""
        logger.info("WebSocket Manager initialized (Supabase Realtime mode)")
        self.cleanup_task = asyncio.create_task(self._cleanup_stale_connections())

    async def connect(self, websocket: WebSocket, user_id: str):
        """Accept WebSocket connection and register user"""
        await websocket.accept()
        
        if user_id not in self.active_connections:
            self.active_connections[user_id] = []
        
        self.active_connections[user_id].append(websocket)
        
        # Update online status
        if user_id not in self.online_users:
            self.online_users.add(user_id)
            await self._broadcast_presence(user_id, "online")
            
            # Subscribe to Supabase Realtime for this user
            await self._subscribe_to_realtime(user_id)
        
        logger.info(f"User {user_id} connected. Total online: {len(self.online_users)}")
    
    def disconnect(self, websocket: WebSocket, user_id: str):
        """Remove WebSocket connection and update online status"""
        if user_id in self.active_connections:
            self.active_connections[user_id].remove(websocket)
            
            # If no more connections, user is offline
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]
                self.online_users.discard(user_id)
                
                # Broadcast offline status
                asyncio.create_task(self._broadcast_presence(user_id, "offline"))
                
                # Unsubscribe from Supabase Realtime
                asyncio.create_task(self._unsubscribe_from_realtime(user_id))
        
        logger.info(f"User {user_id} disconnected")
    
    async def _subscribe_to_realtime(self, user_id: str):
        """Subscribe to Supabase Realtime channels for this user"""
        try:
            # Channel for user-specific notifications
            channel = supabase.channel(f"user:{user_id}")
            
            def handle_realtime(payload):
                """Handle real-time messages from Supabase"""
                asyncio.create_task(self._handle_supabase_realtime(payload))
            
            # Listen for new messages
            channel.on_postgres_changes(
                event="INSERT",
                schema="public",
                table="messages",
                filter=f"recipient_id=eq.{user_id}",
                callback=handle_realtime
            )
            
            # Listen for message status updates
            channel.on_postgres_changes(
                event="UPDATE",
                schema="public",
                table="messages",
                filter=f"recipient_id=eq.{user_id}",
                callback=handle_realtime
            )
            
            # Subscribe
            channel.subscribe()
            self.realtime_channels[user_id] = channel
            logger.info(f"User {user_id} subscribed to Supabase Realtime")
            
        except Exception as e:
            logger.error(f"Failed to subscribe to Supabase Realtime: {e}")
    
    async def _unsubscribe_from_realtime(self, user_id: str):
        """Unsubscribe from Supabase Realtime channels"""
        if user_id in self.realtime_channels:
            try:
                self.realtime_channels[user_id].unsubscribe()
                del self.realtime_channels[user_id]
            except Exception as e:
                logger.error(f"Failed to unsubscribe: {e}")
    
    async def _handle_supabase_realtime(self, payload):
        """Handle incoming messages from Supabase Realtime"""
        try:
            record = payload.get('record', {})
            event = payload.get('event', '')
            
            # Determine message type
            if event == 'INSERT' and 'messages' in payload.get('table', ''):
                # New message
                await self._handle_new_message(record)
            elif event == 'UPDATE' and 'messages' in payload.get('table', ''):
                # Message status update (read/delivered)
                await self._handle_status_update(record)
                
        except Exception as e:
            logger.error(f"Error handling Supabase realtime: {e}")
    
    async def _handle_new_message(self, message_data: dict):
        """Handle new message from Supabase"""
        recipient_id = message_data.get('recipient_id')
        if recipient_id and recipient_id in self.active_connections:
            await self.send_message({
                "type": "new_message",
                "data": message_data,
                "timestamp": datetime.utcnow().isoformat()
            }, recipient_id)
    
    async def _handle_status_update(self, message_data: dict):
        """Handle message status update"""
        # Send read/delivered receipt to sender
        sender_id = message_data.get('sender_id')
        if sender_id and sender_id in self.active_connections:
            await self.send_message({
                "type": "message_status",
                "data": {
                    "message_id": message_data.get('id'),
                    "status": message_data.get('status'),
                    "is_read": message_data.get('is_read', False),
                    "is_delivered": message_data.get('is_delivered', False),
                    "timestamp": datetime.utcnow().isoformat()
                }
            }, sender_id)
    
    async def send_message(self, message_data: Dict[str, Any], recipient_id: str):
        """Send message to specific user"""
        if recipient_id in self.active_connections:
            for connection in self.active_connections[recipient_id]:
                try:
                    await connection.send_json(message_data)
                except Exception as e:
                    logger.error(f"Failed to send message to {recipient_id}: {e}")
    
    async def broadcast_to_chat(self, chat_id: str, message: Dict[str, Any], exclude_user_id: Optional[str] = None):
        """Broadcast to all participants in a chat"""
        # Get chat participants from Supabase
        try:
            result = supabase.table("chats") \
                .select("participants") \
                .eq("id", chat_id) \
                .execute()
            
            if not result.data:
                return
            
            participants = result.data[0].get('participants', [])
            
            # Send to each online participant
            for user_id in participants:
                if user_id != exclude_user_id and user_id in self.active_connections:
                    await self.send_message(message, user_id)
                    
        except Exception as e:
            logger.error(f"Failed to broadcast to chat: {e}")
    
    async def set_typing(self, chat_id: str, user_id: str, is_typing: bool):
        """Update typing status for a chat"""
        if chat_id not in self.typing_status:
            self.typing_status[chat_id] = set()
        
        if is_typing:
            self.typing_status[chat_id].add(user_id)
        else:
            self.typing_status[chat_id].discard(user_id)
        
        # Broadcast to chat
        await self.broadcast_to_chat(chat_id, {
            "type": "typing",
            "data": {
                "chat_id": chat_id,
                "user_id": user_id,
                "is_typing": is_typing,
                "typing_users": list(self.typing_status.get(chat_id, set()))
            }
        }, exclude_user_id=user_id)
    
    async def send_read_receipt(self, message_id: str, user_id: str, chat_id: str):
        """Send read receipt to message sender"""
        try:
            # Get message sender from Supabase
            result = supabase.table("messages") \
                .select("sender_id") \
                .eq("id", message_id) \
                .execute()
            
            if result.data and result.data[0].get('sender_id'):
                sender_id = result.data[0]['sender_id']
                await self.send_message({
                    "type": "read_receipt",
                    "data": {
                        "message_id": message_id,
                        "user_id": user_id,
                        "chat_id": chat_id,
                        "timestamp": datetime.utcnow().isoformat()
                    }
                }, sender_id)
                
        except Exception as e:
            logger.error(f"Failed to send read receipt: {e}")
    
    async def _broadcast_presence(self, user_id: str, status: str):
        """Broadcast user presence to followers"""
        try:
            # Get user's followers from Supabase
            result = supabase.table("follows") \
                .select("follower_id") \
                .eq("following_id", user_id) \
                .execute()
            
            if result.data:
                follower_ids = [f['follower_id'] for f in result.data]
                
                for follower_id in follower_ids:
                    await self.send_message({
                        "type": "presence",
                        "data": {
                            "user_id": user_id,
                            "status": status,
                            "timestamp": datetime.utcnow().isoformat()
                        }
                    }, follower_id)
                    
        except Exception as e:
            logger.error(f"Failed to broadcast presence: {e}")
    
    async def get_online_status(self, user_id: str) -> bool:
        """Check if user is online"""
        return user_id in self.online_users
    
    async def get_online_friends(self, user_id: str) -> List[str]:
        """Get online friends/following"""
        try:
            # Get user's following
            result = supabase.table("follows") \
                .select("following_id") \
                .eq("follower_id", user_id) \
                .execute()
            
            if result.data:
                following_ids = [f['following_id'] for f in result.data]
                return [uid for uid in following_ids if uid in self.online_users]
            return []
            
        except Exception as e:
            logger.error(f"Failed to get online friends: {e}")
            return []
    
    async def send_notification(self, user_id: str, notification: Dict[str, Any]):
        """Send push notification to user"""
        await self.send_message({
            "type": "notification",
            "data": notification
        }, user_id)
    
    async def _cleanup_stale_connections(self):
        """Periodically clean up stale connections"""
        while True:
            await asyncio.sleep(300)  # Every 5 minutes
            
            for user_id, connections in list(self.active_connections.items()):
                for conn in connections[:]:
                    try:
                        # Send ping to check connection
                        await conn.send_json({"type": "ping"})
                    except:
                        # Connection is dead, remove it
                        connections.remove(conn)
                
                # If no connections left, mark offline
                if not connections:
                    del self.active_connections[user_id]
                    self.online_users.discard(user_id)
                    await self._broadcast_presence(user_id, "offline")
                    await self._unsubscribe_from_realtime(user_id)
    
    async def cleanup(self):
        """Clean up all resources"""
        if self.cleanup_task:
            self.cleanup_task.cancel()
        
        # Unsubscribe from all Realtime channels
        for user_id, channel in self.realtime_channels.items():
            try:
                channel.unsubscribe()
            except:
                pass
        
        # Close all WebSocket connections
        for user_id, connections in self.active_connections.items():
            for conn in connections:
                try:
                    await conn.close()
                except:
                    pass
        
        self.active_connections.clear()
        self.online_users.clear()
        self.typing_status.clear()
        self.realtime_channels.clear()
        
        logger.info("WebSocket Manager cleaned up")

# Global instance
manager = ConnectionManager()