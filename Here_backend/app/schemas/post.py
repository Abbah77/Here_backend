from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

class PostBase(BaseModel):
    text: Optional[str] = None
    media_url: Optional[str] = None
    media_type: Optional[str] = None  # 'image', 'video', 'gallery'

class PostCreate(PostBase):
    pass

class PostUpdate(BaseModel):
    text: Optional[str] = None

class PostResponse(PostBase):
    id: str
    author_id: str
    author_name: str
    author_username: str
    author_profile_pic: Optional[str] = None
    like_count: int
    comment_count: int
    share_count: int
    heat_score: float
    is_liked: bool = False
    is_bookmarked: bool = False
    created_at: datetime
    
    class Config:
        from_attributes = True

class FeedResponse(BaseModel):
    posts: List[PostResponse]
    total: int
    page: int
    limit: int
    has_more: bool

class CommentCreate(BaseModel):
    text: str = Field(..., min_length=1, max_length=1000)

class CommentResponse(BaseModel):
    id: str
    post_id: str
    user_id: str
    user_name: str
    user_profile_pic: Optional[str] = None
    text: str
    like_count: int = 0
    created_at: datetime
    
    class Config:
        from_attributes = True