from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime

# Chat schemas
class ChatCreate(BaseModel):
    participant_ids: List[str]
    name: Optional[str] = None

class ChatParticipant(BaseModel):
    id: str
    full_name: str
    username: str
    profile_pic_url: Optional[str] = None

class ChatResponse(BaseModel):
    id: str
    type: str  # 'direct' or 'group'
    name: Optional[str] = None
    participants: List[str]
    participant_details: Optional[List[ChatParticipant]] = None
    created_by: str
    created_at: datetime
    updated_at: datetime
    last_message: Optional['MessageResponse'] = None
    unread_count: int = 0
    
    class Config:
        from_attributes = True

class ChatListResponse(BaseModel):
    id: str
    type: str
    name: Optional[str] = None
    last_message: Optional[str] = None
    last_message_time: Optional[datetime] = None
    last_message_sender: Optional[str] = None
    unread_count: int = 0
    participants: List[str]
    
    class Config:
        from_attributes = True

# Message schemas
class MessageCreate(BaseModel):
    chat_id: str
    text: Optional[str] = None
    media_url: Optional[str] = None
    media_type: Optional[str] = None
    temp_id: Optional[str] = None

class MessageResponse(BaseModel):
    id: str
    chat_id: str
    sender_id: str
    sender_name: Optional[str] = None
    sender_profile_pic: Optional[str] = None
    text: Optional[str] = None
    media_url: Optional[str] = None
    media_type: Optional[str] = None
    status: str  # 'sent', 'delivered', 'read'
    is_read: bool
    is_delivered: bool
    created_at: datetime
    delivered_at: Optional[datetime] = None
    read_at: Optional[datetime] = None
    temp_id: Optional[str] = None
    
    class Config:
        from_attributes = True

class MessageSyncResponse(BaseModel):
    messages: List[MessageResponse]
    has_more: bool
    last_sync: datetime

class TypingIndicator(BaseModel):
    chat_id: str
    user_id: str
    is_typing: bool
    timestamp: datetime = Field(default_factory=datetime.utcnow)