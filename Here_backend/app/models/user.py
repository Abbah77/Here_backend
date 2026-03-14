from pydantic import BaseModel, EmailStr, Field, validator
from typing import Optional, Dict, Any, List
from datetime import datetime
import uuid
import re

# ============= Pydantic Models for Validation =============

class UserBase(BaseModel):
    """Base user schema for validation"""
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=50)
    full_name: str = Field(..., min_length=1, max_length=100)
    
    @validator('username')
    def validate_username(cls, v):
        if not re.match("^[a-zA-Z0-9_.]+$", v):
            raise ValueError('Username must contain only letters, numbers, dots and underscores')
        return v

class UserCreate(UserBase):
    """Schema for creating a user"""
    password: str = Field(..., min_length=6)
    bio: Optional[str] = None
    profile_pic_url: Optional[str] = None
    settings: Optional[Dict[str, Any]] = None

class UserUpdate(BaseModel):
    """Schema for updating a user"""
    full_name: Optional[str] = None
    bio: Optional[str] = None
    profile_pic_url: Optional[str] = None
    settings: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None

class UserInDB(BaseModel):
    """Schema for user as stored in DB (what we return)"""
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
    """User response schema (same as InDB for now)"""
    pass

class FollowResponse(BaseModel):
    """Schema for follow relationship"""
    follower_id: str
    following_id: str
    created_at: datetime
    
    class Config:
        from_attributes = True

class UserSearchResponse(BaseModel):
    """Schema for user search results"""
    users: List[UserResponse]
    total: int

# ============= SQLAlchemy Model (Optional - for reference) =============
# You can keep this if you want to use SQLAlchemy alongside Supabase
# If not, you can delete everything below this line

"""
from sqlalchemy import Column, String, Integer, Boolean, DateTime, Text, JSON, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from ..core.database import Base

class User(Base):
    __tablename__ = "users"
    
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String(255), unique=True, nullable=False, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    full_name = Column(String(100), nullable=False)
    hashed_password = Column(String(255), nullable=False)
    
    # Profile
    bio = Column(Text, nullable=True)
    profile_pic_url = Column(String(500), nullable=True)
    is_verified = Column(Boolean, default=False)
    
    # Stats
    follower_count = Column(Integer, default=0)
    following_count = Column(Integer, default=0)
    post_count = Column(Integer, default=0)
    heat_score = Column(Integer, default=0)
    
    # Settings
    settings = Column(JSON, default={
        "notifications": True,
        "privacy": "public",
        "theme": "system"
    })
    
    # Auth
    is_active = Column(Boolean, default=True)
    last_login = Column(DateTime(timezone=True), nullable=True)
    last_active = Column(DateTime(timezone=True), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # AI/ML
    embedding = Column(JSON, nullable=True)
    
    # Relationships
    sent_messages = relationship("Message", foreign_keys="Message.sender_id", back_populates="sender")
    received_messages = relationship("Message", foreign_keys="Message.recipient_id", back_populates="recipient")
    posts = relationship("Post", back_populates="author", cascade="all, delete-orphan")
    post_likes = relationship("PostLike", back_populates="user")
    comments = relationship("Comment", back_populates="user")
    
    # Follow relationships
    followers = relationship(
        "Follow", 
        foreign_keys="Follow.following_id", 
        back_populates="following",
        cascade="all, delete-orphan"
    )
    following = relationship(
        "Follow", 
        foreign_keys="Follow.follower_id", 
        back_populates="follower",
        cascade="all, delete-orphan"
    )

class Follow(Base):
    __tablename__ = "follows"
    
    follower_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    following_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    follower = relationship("User", foreign_keys=[follower_id], back_populates="following")
    following = relationship("User", foreign_keys=[following_id], back_populates="followers")
"""

# ============= User Service for Supabase =============
# This is a helper service to interact with Supabase

from typing import Optional, List, Dict, Any
from datetime import datetime
from ..core.database import supabase
from ..core.security import SecurityUtils

class UserService:
    
    @staticmethod
    async def create_user(user_data: UserCreate) -> Optional[UserInDB]:
        """Create a new user in Supabase"""
        try:
            # Hash password
            hashed_password = SecurityUtils.get_password_hash(user_data.password)
            
            # Prepare data for insert
            data = {
                "email": user_data.email,
                "username": user_data.username,
                "full_name": user_data.full_name,
                "hashed_password": hashed_password,
                "bio": user_data.bio,
                "profile_pic_url": user_data.profile_pic_url,
                "settings": user_data.settings or {
                    "notifications": True,
                    "privacy": "public",
                    "theme": "system"
                }
            }
            
            # Insert into Supabase
            result = supabase.table("users").insert(data).execute()
            
            if result.data:
                return UserInDB(**result.data[0])
            return None
            
        except Exception as e:
            print(f"Error creating user: {e}")
            return None
    
    @staticmethod
    async def get_user_by_id(user_id: str) -> Optional[UserInDB]:
        """Get user by ID"""
        result = supabase.table("users").select("*").eq("id", user_id).execute()
        if result.data:
            return UserInDB(**result.data[0])
        return None
    
    @staticmethod
    async def get_user_by_email(email: str) -> Optional[UserInDB]:
        """Get user by email"""
        result = supabase.table("users").select("*").eq("email", email).execute()
        if result.data:
            return UserInDB(**result.data[0])
        return None
    
    @staticmethod
    async def get_user_by_username(username: str) -> Optional[UserInDB]:
        """Get user by username"""
        result = supabase.table("users").select("*").eq("username", username).execute()
        if result.data:
            return UserInDB(**result.data[0])
        return None
    
    @staticmethod
    async def update_user(user_id: str, user_data: UserUpdate) -> Optional[UserInDB]:
        """Update user"""
        update_data = user_data.dict(exclude_unset=True)
        if update_data:
            update_data["updated_at"] = datetime.utcnow().isoformat()
            result = supabase.table("users").update(update_data).eq("id", user_id).execute()
            if result.data:
                return UserInDB(**result.data[0])
        return None
    
    @staticmethod
    async def update_last_login(user_id: str):
        """Update user's last login time"""
        supabase.table("users").update({
            "last_login": datetime.utcnow().isoformat()
        }).eq("id", user_id).execute()
    
    @staticmethod
    async def update_last_active(user_id: str):
        """Update user's last active time"""
        supabase.table("users").update({
            "last_active": datetime.utcnow().isoformat()
        }).eq("id", user_id).execute()
    
    @staticmethod
    async def follow_user(follower_id: str, following_id: str):
        """Follow a user"""
        supabase.table("follows").insert({
            "follower_id": follower_id,
            "following_id": following_id
        }).execute()
        
        # Update follower counts
        supabase.table("users").update({
            "following_count": supabase.raw("following_count + 1")
        }).eq("id", follower_id).execute()
        
        supabase.table("users").update({
            "follower_count": supabase.raw("follower_count + 1")
        }).eq("id", following_id).execute()
    
    @staticmethod
    async def unfollow_user(follower_id: str, following_id: str):
        """Unfollow a user"""
        supabase.table("follows").delete().eq("follower_id", follower_id).eq("following_id", following_id).execute()
        
        # Update follower counts
        supabase.table("users").update({
            "following_count": supabase.raw("following_count - 1")
        }).eq("id", follower_id).execute()
        
        supabase.table("users").update({
            "follower_count": supabase.raw("follower_count - 1")
        }).eq("id", following_id).execute()
    
    @staticmethod
    async def search_users(query: str, limit: int = 20) -> List[UserInDB]:
        """Search users by username or full name"""
        result = supabase.table("users").select("*")\
            .or_(f"username.ilike.%{query}%,full_name.ilike.%{query}%")\
            .limit(limit).execute()
        
        return [UserInDB(**item) for item in result.data]