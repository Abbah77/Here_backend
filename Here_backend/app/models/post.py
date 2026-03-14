# You'll need Pydantic models for posts
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

class Post(BaseModel):
    id: str
    author_id: str
    author_name: str
    author_username: str
    author_profile_pic: Optional[str]
    text: Optional[str]
    media_url: Optional[str]
    media_type: Optional[str]
    like_count: int
    comment_count: int
    share_count: int
    heat_score: float
    is_deleted: bool
    created_at: datetime
    updated_at: Optional[datetime]
    
    class Config:
        from_attributes = True