from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

class Message(BaseModel):
    id: str
    chat_id: str
    sender_id: str
    text: Optional[str]
    media_url: Optional[str]
    media_type: Optional[str]
    status: str
    is_read: bool
    is_delivered: bool
    created_at: datetime
    delivered_at: Optional[datetime]
    read_at: Optional[datetime]
    
    class Config:
        from_attributes = True

class Chat(BaseModel):
    id: str
    type: str
    name: Optional[str]
    participants: List[str]
    created_by: str
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True