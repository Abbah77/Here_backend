from fastapi import WebSocket, WebSocketDisconnect, APIRouter
from ...core.database import supabase
from ...core.security import SecurityUtils
import json

router = APIRouter()

class ConnectionManager:
    def __init__(self):
        self.active_connections = {}
    
    async def connect(self, websocket: WebSocket, user_id: str):
        await websocket.accept()
        if user_id not in self.active_connections:
            self.active_connections[user_id] = []
        self.active_connections[user_id].append(websocket)
    
    def disconnect(self, websocket: WebSocket, user_id: str):
        if user_id in self.active_connections:
            self.active_connections[user_id].remove(websocket)
    
    async def send_personal_message(self, message: dict, user_id: str):
        if user_id in self.active_connections:
            for connection in self.active_connections[user_id]:
                try:
                    await connection.send_json(message)
                except:
                    pass

manager = ConnectionManager()

@router.websocket("/ws/{user_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    user_id: str,
    token: str
):
    # Authenticate
    payload = SecurityUtils.decode_token(token)
    if not payload or payload.get("sub") != user_id:
        await websocket.close(code=1008)
        return
    
    await manager.connect(websocket, user_id)
    
    # Subscribe to Supabase Realtime channels
    channel = supabase.channel(f"user:{user_id}")
    
    def handle_realtime(payload):
        # Send real-time updates via WebSocket
        asyncio.create_task(
            manager.send_personal_message(payload, user_id)
        )
    
    channel.on_postgres_changes(
        event="INSERT",
        schema="public",
        table="messages",
        callback=handle_realtime
    )
    
    channel.subscribe()
    
    try:
        while True:
            data = await websocket.receive_json()
            # Handle client messages
            if data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        manager.disconnect(websocket, user_id)
        channel.unsubscribe()