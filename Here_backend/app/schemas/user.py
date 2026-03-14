from pydantic import BaseModel, EmailStr, Field, validator
from typing import Optional, Dict, Any, List
from datetime import datetime
import re

class UserBase(BaseModel):
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=50)
    full_name: str = Field(..., min_length=1, max_length=100)
    
    @validator('username')
    def validate_username(cls, v):
        if not re.match("^[a-zA-Z0-9_.]+$", v):
            raise ValueError('Username must contain only letters, numbers, dots and underscores')
        return v

class UserCreate(UserBase):
    password: str = Field(..., min_length=6)
    bio: Optional[str] = None
    profile_pic_url: Optional[str] = None
    settings: Optional[Dict[str, Any]] = None

class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    bio: Optional[str] = None
    profile_pic_url: Optional[str] = None
    settings: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None

class UserInDB(BaseModel):
    id: str
    email: str
    username: str
    full_name: str
    bio: Optional[str] = None
    profile_pic_url: Optional[str] = None
    is_verified: bool
    follower_count: int
    following_count: int
    post_count: int
    heat_score: int
    settings: Dict[str, Any]
    is_active: bool
    last_login: Optional[datetime]
    last_active: Optional[datetime]
    created_at: datetime
    updated_at: Optional[datetime]
    embedding: Optional[Dict[str, Any]] = None
    
    class Config:
        from_attributes = True

class UserResponse(UserInDB):
    pass

class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

class RefreshToken(BaseModel):
    refresh_token: str