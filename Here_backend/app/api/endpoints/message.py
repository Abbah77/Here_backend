from fastapi import APIRouter, Depends, HTTPException, status, Query, WebSocket, WebSocketDisconnect
from typing import List, Optional
from datetime import datetime
import uuid

from ...core.database import supabase
from ...core.security import SecurityUtils
from ...core.config import settings
from ...models.user import UserInDB
from ...services.user_service import UserService
from ..endpoints.auth import get_current_user_dependency

router = APIRouter(prefix="/messages", tags=["messages"])

# ============= CHAT MANAGEMENT =============

@router.post("/chats")
async def create_chat(
    *,
    participant_ids: List[str],
    name: Optional[str] = None,
    current_user: UserInDB = Depends(get_current_user_dependency)
):
    """Create a new chat (direct or group)"""
    
    # Add current user to participants
    all_participants = list(set([current_user.id] + participant_ids))
    
    # Check if direct chat already exists
    if len(all_participants) == 2:
        # Look for existing direct chat
        existing = supabase.table("chats") \
            .select("*") \
            .eq("type", "direct") \
            .contains("participants", all_participants) \
            .execute()
        
        if existing.data:
            return existing.data[0]
    
    # Create new chat
    chat_data = {
        "id": str(uuid.uuid4()),
        "type": "direct" if len(all_participants) == 2 else "group",
        "name": name,
        "participants": all_participants,
        "created_by": current_user.id,
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat()
    }
    
    result = supabase.table("chats").insert(chat_data).execute()
    
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create chat"
        )
    
    return result.data[0]

@router.get("/chats")
async def get_user_chats(
    current_user: UserInDB = Depends(get_current_user_dependency),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100)
):
    """Get all chats for current user"""
    
    # Find all chats where user is a participant
    result = supabase.table("chats") \
        .select("*") \
        .contains("participants", [current_user.id]) \
        .order("updated_at", desc=True) \
        .range(skip, skip + limit - 1) \
        .execute()
    
    chats = result.data if result.data else []
    
    # For each chat, get last message and unread count
    for chat in chats:
        # Get last message
        last_msg = supabase.table("messages") \
            .select("*") \
            .eq("chat_id", chat['id']) \
            .order("created_at", desc=True) \
            .limit(1) \
            .execute()
        
        chat['last_message'] = last_msg.data[0] if last_msg.data else None
        
        # Get unread count
        unread = supabase.table("messages") \
            .select("*", count="exact") \
            .eq("chat_id", chat['id']) \
            .eq("is_read", False) \
            .neq("sender_id", current_user.id) \
            .execute()
        
        chat['unread_count'] = unread.count if hasattr(unread, 'count') else 0
    
    return chats

@router.get("/chats/{chat_id}")
async def get_chat(
    chat_id: str,
    current_user: UserInDB = Depends(get_current_user_dependency)
):
    """Get chat details"""
    
    result = supabase.table("chats") \
        .select("*") \
        .eq("id", chat_id) \
        .execute()
    
    if not result.data:
        raise HTTPException(status_code=404, detail="Chat not found")
    
    chat = result.data[0]
    
    # Check if user is participant
    if current_user.id not in chat.get('participants', []):
        raise HTTPException(status_code=403, detail="Not a participant in this chat")
    
    # Get participant details
    participant_ids = chat.get('participants', [])
    users_result = supabase.table("users") \
        .select("id, full_name, username, profile_pic_url") \
        .in_("id", participant_ids) \
        .execute()
    
    chat['participant_details'] = users_result.data if users_result.data else []
    
    return chat

# ============= MESSAGE OPERATIONS =============

@router.post("")
async def send_message(
    *,
    chat_id: str,
    text: Optional[str] = None,
    media_url: Optional[str] = None,
    media_type: Optional[str] = None,
    temp_id: Optional[str] = None,
    current_user: UserInDB = Depends(get_current_user_dependency)
):
    """Send a new message"""
    
    # Verify chat exists and user is participant
    chat_result = supabase.table("chats") \
        .select("*") \
        .eq("id", chat_id) \
        .execute()
    
    if not chat_result.data:
        raise HTTPException(status_code=404, detail="Chat not found")
    
    chat = chat_result.data[0]
    
    if current_user.id not in chat.get('participants', []):
        raise HTTPException(status_code=403, detail="Not a participant in this chat")
    
    # Create message
    message_data = {
        "id": str(uuid.uuid4()),
        "chat_id": chat_id,
        "sender_id": current_user.id,
        "text": text,
        "media_url": media_url,
        "media_type": media_type,
        "status": "sent",
        "is_read": False,
        "is_delivered": False,
        "created_at": datetime.utcnow().isoformat()
    }
    
    result = supabase.table("messages").insert(message_data).execute()
    
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send message"
        )
    
    # Update chat's last message time
    supabase.table("chats") \
        .update({"updated_at": datetime.utcnow().isoformat()}) \
        .eq("id", chat_id) \
        .execute()
    
    message = result.data[0]
    
    # Add temp_id if provided (for client-side tracking)
    if temp_id:
        message['temp_id'] = temp_id
    
    return message

@router.get("/sync")
async def sync_messages(
    chat_id: str = Query(...),
    since: Optional[str] = Query(None),
    current_user: UserInDB = Depends(get_current_user_dependency),
    limit: int = Query(100, ge=1, le=500)
):
    """Delta sync for messages - get only new/changed messages"""
    
    # Verify user is participant
    chat_result = supabase.table("chats") \
        .select("*") \
        .eq("id", chat_id) \
        .execute()
    
    if not chat_result.data:
        raise HTTPException(status_code=404, detail="Chat not found")
    
    chat = chat_result.data[0]
    
    if current_user.id not in chat.get('participants', []):
        raise HTTPException(status_code=403, detail="Not a participant in this chat")
    
    # Build query
    query = supabase.table("messages") \
        .select("*") \
        .eq("chat_id", chat_id) \
        .order("created_at", desc=True) \
        .limit(limit)
    
    if since:
        query = query.gt("created_at", since)
    
    result = query.execute()
    
    messages = result.data if result.data else []
    
    # Mark messages as delivered
    for msg in messages:
        if msg['sender_id'] != current_user.id and not msg['is_delivered']:
            supabase.table("messages") \
                .update({"is_delivered": True}) \
                .eq("id", msg['id']) \
                .execute()
    
    return {
        "messages": messages,
        "has_more": len(messages) == limit,
        "last_sync": datetime.utcnow().isoformat()
    }

@router.get("/chat/{chat_id}")
async def get_chat_messages(
    chat_id: str,
    current_user: UserInDB = Depends(get_current_user_dependency),
    before: Optional[str] = None,
    limit: int = Query(50, ge=1, le=100)
):
    """Get messages for a specific chat (paginated)"""
    
    # Verify user is participant
    chat_result = supabase.table("chats") \
        .select("*") \
        .eq("id", chat_id) \
        .execute()
    
    if not chat_result.data:
        raise HTTPException(status_code=404, detail="Chat not found")
    
    chat = chat_result.data[0]
    
    if current_user.id not in chat.get('participants', []):
        raise HTTPException(status_code=403, detail="Not a participant in this chat")
    
    # Build query
    query = supabase.table("messages") \
        .select("*") \
        .eq("chat_id", chat_id) \
        .order("created_at", desc=True) \
        .limit(limit)
    
    if before:
        query = query.lt("created_at", before)
    
    result = query.execute()
    
    return result.data if result.data else []

@router.patch("/{message_id}/read")
async def mark_message_read(
    message_id: str,
    current_user: UserInDB = Depends(get_current_user_dependency)
):
    """Mark message as read"""
    
    # Get message
    msg_result = supabase.table("messages") \
        .select("*") \
        .eq("id", message_id) \
        .execute()
    
    if not msg_result.data:
        raise HTTPException(status_code=404, detail="Message not found")
    
    message = msg_result.data[0]
    
    # Can't mark own message as read
    if message['sender_id'] == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot mark own message as read")
    
    # Update message
    supabase.table("messages") \
        .update({
            "is_read": True,
            "status": "read",
            "read_at": datetime.utcnow().isoformat()
        }) \
        .eq("id", message_id) \
        .execute()
    
    return {"status": "marked as read"}

@router.patch("/{message_id}/delivered")
async def mark_message_delivered(
    message_id: str,
    current_user: UserInDB = Depends(get_current_user_dependency)
):
    """Mark message as delivered"""
    
    # Get message
    msg_result = supabase.table("messages") \
        .select("*") \
        .eq("id", message_id) \
        .execute()
    
    if not msg_result.data:
        raise HTTPException(status_code=404, detail="Message not found")
    
    message = msg_result.data[0]
    
    # Can't mark own message as delivered
    if message['sender_id'] == current_user.id:
        return {"status": "already sent"}  # Not an error, just ignore
    
    # Update message
    supabase.table("messages") \
        .update({
            "is_delivered": True,
            "status": "delivered",
            "delivered_at": datetime.utcnow().isoformat()
        }) \
        .eq("id", message_id) \
        .execute()
    
    return {"status": "marked as delivered"}

@router.delete("/{message_id}")
async def delete_message(
    message_id: str,
    current_user: UserInDB = Depends(get_current_user_dependency)
):
    """Delete a message"""
    
    # Get message
    msg_result = supabase.table("messages") \
        .select("*") \
        .eq("id", message_id) \
        .execute()
    
    if not msg_result.data:
        raise HTTPException(status_code=404, detail="Message not found")
    
    message = msg_result.data[0]
    
    # Only sender can delete
    if message['sender_id'] != current_user.id:
        raise HTTPException(status_code=403, detail="Can only delete own messages")
    
    # Delete message
    supabase.table("messages") \
        .delete() \
        .eq("id", message_id) \
        .execute()
    
    return {"status": "deleted"}

# ============= TYPING INDICATORS =============

@router.post("/typing")
async def send_typing_indicator(
    chat_id: str,
    is_typing: bool = True,
    current_user: UserInDB = Depends(get_current_user_dependency)
):
    """Send typing indicator to chat"""
    
    # Store typing status in Redis or Supabase (you could use a separate table)
    # For now, just return success - WebSocket handles real-time
    
    return {
        "chat_id": chat_id,
        "user_id": current_user.id,
        "is_typing": is_typing,
        "timestamp": datetime.utcnow().isoformat()
    }

# ============= SEARCH =============

@router.get("/search")
async def search_messages(
    chat_id: str,
    query: str,
    current_user: UserInDB = Depends(get_current_user_dependency),
    limit: int = Query(50, ge=1, le=100)
):
    """Search messages in a chat"""
    
    # Verify user is participant
    chat_result = supabase.table("chats") \
        .select("*") \
        .eq("id", chat_id) \
        .execute()
    
    if not chat_result.data:
        raise HTTPException(status_code=404, detail="Chat not found")
    
    chat = chat_result.data[0]
    
    if current_user.id not in chat.get('participants', []):
        raise HTTPException(status_code=403, detail="Not a participant in this chat")
    
    # Search messages
    result = supabase.table("messages") \
        .select("*") \
        .eq("chat_id", chat_id) \
        .ilike("text", f"%{query}%") \
        .limit(limit) \
        .execute()
    
    return result.data if result.data else []

# ============= UNREAD COUNTS =============

@router.get("/unread")
async def get_unread_counts(
    current_user: UserInDB = Depends(get_current_user_dependency)
):
    """Get unread message counts for all chats"""
    
    # Get all user's chats
    chats_result = supabase.table("chats") \
        .select("id") \
        .contains("participants", [current_user.id]) \
        .execute()
    
    if not chats_result.data:
        return {}
    
    chat_ids = [chat['id'] for chat in chats_result.data]
    
    # Get unread counts
    result = supabase.table("messages") \
        .select("chat_id", count="exact") \
        .in_("chat_id", chat_ids) \
        .eq("is_read", False) \
        .neq("sender_id", current_user.id) \
        .execute()
    
    # Format response
    unread_counts = {}
    if result.data:
        # This is simplified - you might need to group by chat_id
        pass
    
    return unread_counts

# ============= DELETE CHAT =============

@router.delete("/chats/{chat_id}")
async def delete_chat(
    chat_id: str,
    current_user: UserInDB = Depends(get_current_user_dependency)
):
    """Delete a chat and all its messages"""
    
    # Verify user is participant
    chat_result = supabase.table("chats") \
        .select("*") \
        .eq("id", chat_id) \
        .execute()
    
    if not chat_result.data:
        raise HTTPException(status_code=404, detail="Chat not found")
    
    chat = chat_result.data[0]
    
    if current_user.id not in chat.get('participants', []):
        raise HTTPException(status_code=403, detail="Not a participant in this chat")
    
    # Delete all messages first
    supabase.table("messages") \
        .delete() \
        .eq("chat_id", chat_id) \
        .execute()
    
    # Delete chat
    supabase.table("chats") \
        .delete() \
        .eq("id", chat_id) \
        .execute()
    
    return {"status": "deleted"}