from pydantic import BaseModel, EmailStr, Field, validator
from typing import Optional, Dict, Any, List
from datetime import datetime
import re
from ..core.database import supabase
from ..core.security import SecurityUtils

# ============= Pydantic Models for Validation =============

class UserBase(BaseModel):
    """Base user schema for validation"""
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=50)
    
    # ALIAS: This allows Flutter's 'name' to map to 'full_name'
    full_name: str = Field(..., min_length=1, max_length=100, alias="name")
    
    @validator('username')
    def validate_username(cls, v):
        if not re.match("^[a-zA-Z0-9_.]+$", v):
            raise ValueError('Username must contain only letters, numbers, dots and underscores')
        return v

    class Config:
        allow_population_by_field_name = True
        populate_by_name = True 

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
    """Schema for user as stored in DB (INTERNAL USE)"""
    id: str
    email: str
    username: str
    full_name: str
    # FIX: Added this field so SecurityUtils can verify the password!
    hashed_password: str 
    bio: Optional[str] = None
    profile_pic_url: Optional[str] = None
    is_verified: bool = False
    follower_count: int = 0
    following_count: int = 0
    post_count: int = 0
    heat_score: int = 0
    settings: Dict[str, Any] = {}
    is_active: bool = True
    last_login: Optional[datetime] = None
    last_active: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = None
    embedding: Optional[Dict[str, Any]] = None
    
    class Config:
        from_attributes = True

class UserResponse(BaseModel):
    """User response schema (STRICTLY FOR RETURNING TO FLUTTER)"""
    # We exclude hashed_password here for security
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
    created_at: datetime

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

# ============= User Service for Supabase =============

class UserService:
    
    @staticmethod
    async def create_user(user_data: UserCreate) -> Optional[UserInDB]:
        """Create a new user in Supabase"""
        try:
            hashed_password = SecurityUtils.get_password_hash(user_data.password)
            
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
            
            result = supabase.table("users").insert(data).execute()
            
            if result.data and len(result.data) > 0:
                return UserInDB(**result.data[0])
            return None
            
        except Exception as e:
            print(f"Error creating user: {e}")
            return None
    
    @staticmethod
    async def get_user_by_id(user_id: str) -> Optional[UserInDB]:
        try:
            result = supabase.table("users").select("*").eq("id", user_id).execute()
            if result.data:
                return UserInDB(**result.data[0])
            return None
        except Exception:
            return None
    
    @staticmethod
    async def get_user_by_email(email: str) -> Optional[UserInDB]:
        try:
            result = supabase.table("users").select("*").eq("email", email).execute()
            if result.data:
                # This now includes hashed_password correctly!
                return UserInDB(**result.data[0])
            return None
        except Exception as e:
            print(f"Error fetching by email: {e}")
            return None
    
    @staticmethod
    async def get_user_by_username(username: str) -> Optional[UserInDB]:
        try:
            result = supabase.table("users").select("*").eq("username", username).execute()
            if result.data:
                return UserInDB(**result.data[0])
            return None
        except Exception:
            return None
    
    @staticmethod
    async def update_user(user_id: str, user_data: UserUpdate) -> Optional[UserInDB]:
        try:
            update_data = user_data.dict(exclude_unset=True)
            if update_data:
                update_data["updated_at"] = datetime.utcnow().isoformat()
                result = supabase.table("users").update(update_data).eq("id", user_id).execute()
                if result.data:
                    return UserInDB(**result.data[0])
            return None
        except Exception:
            return None
