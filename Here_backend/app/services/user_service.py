from typing import Optional, List, Dict, Any
from datetime import datetime
from ..core.database import supabase
from ..core.security import SecurityUtils
from ..models.user import UserInDB, UserCreate, UserUpdate, UserResponse

class UserService:
    """
    Service class for user-related operations with Supabase
    """
    
    @staticmethod
    async def create_user(user_data: UserCreate) -> Optional[UserInDB]:
        """
        Create a new user in Supabase
        
        Args:
            user_data: UserCreate model with user information
            
        Returns:
            UserInDB object if successful, None otherwise
        """
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
                },
                "is_verified": False,
                "follower_count": 0,
                "following_count": 0,
                "post_count": 0,
                "heat_score": 0,
                "is_active": True,
                "created_at": datetime.utcnow().isoformat()
            }
            
            # Insert into Supabase
            result = supabase.table("users").insert(data).execute()
            
            if result.data and len(result.data) > 0:
                return UserInDB(**result.data[0])
            return None
            
        except Exception as e:
            print(f"Error creating user: {e}")
            return None
    
    @staticmethod
    async def get_user_by_id(user_id: str) -> Optional[UserInDB]:
        """
        Get user by ID
        
        Args:
            user_id: User UUID
            
        Returns:
            UserInDB object if found, None otherwise
        """
        try:
            result = supabase.table("users").select("*").eq("id", user_id).execute()
            if result.data and len(result.data) > 0:
                return UserInDB(**result.data[0])
            return None
        except Exception as e:
            print(f"Error getting user by ID: {e}")
            return None
    
    @staticmethod
    async def get_user_by_email(email: str) -> Optional[UserInDB]:
        """
        Get user by email
        
        Args:
            email: User email
            
        Returns:
            UserInDB object if found, None otherwise
        """
        try:
            result = supabase.table("users").select("*").eq("email", email).execute()
            if result.data and len(result.data) > 0:
                return UserInDB(**result.data[0])
            return None
        except Exception as e:
            print(f"Error getting user by email: {e}")
            return None
    
    @staticmethod
    async def get_user_by_username(username: str) -> Optional[UserInDB]:
        """
        Get user by username
        
        Args:
            username: User username
            
        Returns:
            UserInDB object if found, None otherwise
        """
        try:
            result = supabase.table("users").select("*").eq("username", username).execute()
            if result.data and len(result.data) > 0:
                return UserInDB(**result.data[0])
            return None
        except Exception as e:
            print(f"Error getting user by username: {e}")
            return None
    
    @staticmethod
    async def update_user(user_id: str, user_data: UserUpdate) -> Optional[UserInDB]:
        """
        Update user information
        
        Args:
            user_id: User UUID
            user_data: UserUpdate model with fields to update
            
        Returns:
            Updated UserInDB object if successful, None otherwise
        """
        try:
            update_data = user_data.dict(exclude_unset=True)
            if update_data:
                update_data["updated_at"] = datetime.utcnow().isoformat()
                
                result = supabase.table("users") \
                    .update(update_data) \
                    .eq("id", user_id) \
                    .execute()
                    
                if result.data and len(result.data) > 0:
                    return UserInDB(**result.data[0])
            return None
        except Exception as e:
            print(f"Error updating user: {e}")
            return None
    
    @staticmethod
    async def update_last_login(user_id: str):
        """
        Update user's last login time
        
        Args:
            user_id: User UUID
        """
        try:
            supabase.table("users").update({
                "last_login": datetime.utcnow().isoformat()
            }).eq("id", user_id).execute()
        except Exception as e:
            print(f"Error updating last login: {e}")
    
    @staticmethod
    async def update_last_active(user_id: str):
        """
        Update user's last active time
        
        Args:
            user_id: User UUID
        """
        try:
            supabase.table("users").update({
                "last_active": datetime.utcnow().isoformat()
            }).eq("id", user_id).execute()
        except Exception as e:
            print(f"Error updating last active: {e}")
    
    @staticmethod
    async def update_heat_score(user_id: str, new_score: int):
        """
        Update user's heat score
        
        Args:
            user_id: User UUID
            new_score: New heat score value
        """
        try:
            supabase.table("users").update({
                "heat_score": new_score
            }).eq("id", user_id).execute()
        except Exception as e:
            print(f"Error updating heat score: {e}")
    
    @staticmethod
    async def follow_user(follower_id: str, following_id: str) -> bool:
        """
        Follow a user
        
        Args:
            follower_id: User who is following
            following_id: User being followed
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Check if already following
            existing = supabase.table("follows") \
                .select("*") \
                .eq("follower_id", follower_id) \
                .eq("following_id", following_id) \
                .execute()
                
            if existing.data and len(existing.data) > 0:
                return False  # Already following
            
            # Create follow relationship
            supabase.table("follows").insert({
                "follower_id": follower_id,
                "following_id": following_id,
                "created_at": datetime.utcnow().isoformat()
            }).execute()
            
            # Update follower counts
            # Increment following_count for follower
            supabase.table("users").update({
                "following_count": supabase.raw("following_count + 1")
            }).eq("id", follower_id).execute()
            
            # Increment follower_count for following
            supabase.table("users").update({
                "follower_count": supabase.raw("follower_count + 1")
            }).eq("id", following_id).execute()
            
            return True
            
        except Exception as e:
            print(f"Error following user: {e}")
            return False
    
    @staticmethod
    async def unfollow_user(follower_id: str, following_id: str) -> bool:
        """
        Unfollow a user
        
        Args:
            follower_id: User who is unfollowing
            following_id: User being unfollowed
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Delete follow relationship
            result = supabase.table("follows") \
                .delete() \
                .eq("follower_id", follower_id) \
                .eq("following_id", following_id) \
                .execute()
            
            if not result.data:
                return False  # Wasn't following
            
            # Update follower counts
            # Decrement following_count for follower
            supabase.table("users").update({
                "following_count": supabase.raw("GREATEST(following_count - 1, 0)")
            }).eq("id", follower_id).execute()
            
            # Decrement follower_count for following
            supabase.table("users").update({
                "follower_count": supabase.raw("GREATEST(follower_count - 1, 0)")
            }).eq("id", following_id).execute()
            
            return True
            
        except Exception as e:
            print(f"Error unfollowing user: {e}")
            return False
    
    @staticmethod
    async def is_following(follower_id: str, following_id: str) -> bool:
        """
        Check if a user is following another
        
        Args:
            follower_id: Potential follower
            following_id: Potential followee
            
        Returns:
            True if following, False otherwise
        """
        try:
            result = supabase.table("follows") \
                .select("*") \
                .eq("follower_id", follower_id) \
                .eq("following_id", following_id) \
                .execute()
                
            return len(result.data) > 0
        except Exception as e:
            print(f"Error checking follow status: {e}")
            return False
    
    @staticmethod
    async def get_followers(user_id: str, limit: int = 50, offset: int = 0) -> List[UserInDB]:
        """
        Get followers of a user
        
        Args:
            user_id: User UUID
            limit: Maximum number of results
            offset: Pagination offset
            
        Returns:
            List of UserInDB objects
        """
        try:
            result = supabase.table("follows") \
                .select("follower_id, users!follows_follower_id_fkey(*)") \
                .eq("following_id", user_id) \
                .range(offset, offset + limit - 1) \
                .execute()
            
            users = []
            if result.data:
                for item in result.data:
                    if item.get("users"):
                        users.append(UserInDB(**item["users"]))
            return users
        except Exception as e:
            print(f"Error getting followers: {e}")
            return []
    
    @staticmethod
    async def get_following(user_id: str, limit: int = 50, offset: int = 0) -> List[UserInDB]:
        """
        Get users that a user is following
        
        Args:
            user_id: User UUID
            limit: Maximum number of results
            offset: Pagination offset
            
        Returns:
            List of UserInDB objects
        """
        try:
            result = supabase.table("follows") \
                .select("following_id, users!follows_following_id_fkey(*)") \
                .eq("follower_id", user_id) \
                .range(offset, offset + limit - 1) \
                .execute()
            
            users = []
            if result.data:
                for item in result.data:
                    if item.get("users"):
                        users.append(UserInDB(**item["users"]))
            return users
        except Exception as e:
            print(f"Error getting following: {e}")
            return []
    
    @staticmethod
    async def get_follow_counts(user_id: str) -> Dict[str, int]:
        """
        Get follower and following counts for a user
        
        Args:
            user_id: User UUID
            
        Returns:
            Dictionary with follower_count and following_count
        """
        try:
            user = await UserService.get_user_by_id(user_id)
            if user:
                return {
                    "follower_count": user.follower_count,
                    "following_count": user.following_count
                }
            return {"follower_count": 0, "following_count": 0}
        except Exception as e:
            print(f"Error getting follow counts: {e}")
            return {"follower_count": 0, "following_count": 0}
    
    @staticmethod
    async def search_users(query: str, limit: int = 20, offset: int = 0) -> List[UserInDB]:
        """
        Search users by username or full name
        
        Args:
            query: Search query string
            limit: Maximum number of results
            offset: Pagination offset
            
        Returns:
            List of UserInDB objects matching the search
        """
        try:
            result = supabase.table("users") \
                .select("*") \
                .or_(f"username.ilike.%{query}%,full_name.ilike.%{query}%") \
                .range(offset, offset + limit - 1) \
                .execute()
            
            if result.data:
                return [UserInDB(**item) for item in result.data]
            return []
        except Exception as e:
            print(f"Error searching users: {e}")
            return []
    
    @staticmethod
    async def get_trending_users(limit: int = 10) -> List[UserInDB]:
        """
        Get trending users based on heat score
        
        Args:
            limit: Maximum number of results
            
        Returns:
            List of UserInDB objects with highest heat scores
        """
        try:
            result = supabase.table("users") \
                .select("*") \
                .order("heat_score", desc=True) \
                .limit(limit) \
                .execute()
            
            if result.data:
                return [UserInDB(**item) for item in result.data]
            return []
        except Exception as e:
            print(f"Error getting trending users: {e}")
            return []
    
    @staticmethod
    async def delete_user(user_id: str) -> bool:
        """
        Delete a user (soft delete by setting is_active=False)
        
        Args:
            user_id: User UUID
            
        Returns:
            True if successful, False otherwise
        """
        try:
            result = supabase.table("users") \
                .update({"is_active": False, "updated_at": datetime.utcnow().isoformat()}) \
                .eq("id", user_id) \
                .execute()
                
            return len(result.data) > 0
        except Exception as e:
            print(f"Error deleting user: {e}")
            return False
    
    @staticmethod
    async def get_user_stats(user_id: str) -> Dict[str, Any]:
        """
        Get comprehensive user statistics
        
        Args:
            user_id: User UUID
            
        Returns:
            Dictionary with user statistics
        """
        try:
            user = await UserService.get_user_by_id(user_id)
            if not user:
                return {}
            
            # Get post count (assuming posts table exists)
            posts_result = supabase.table("posts") \
                .select("id", count="exact") \
                .eq("author_id", user_id) \
                .execute()
            
            post_count = posts_result.count if hasattr(posts_result, 'count') else user.post_count
            
            return {
                "user_id": user.id,
                "username": user.username,
                "full_name": user.full_name,
                "post_count": post_count,
                "follower_count": user.follower_count,
                "following_count": user.following_count,
                "heat_score": user.heat_score,
                "is_verified": user.is_verified,
                "joined_at": user.created_at.isoformat() if user.created_at else None
            }
        except Exception as e:
            print(f"Error getting user stats: {e}")
            return {}