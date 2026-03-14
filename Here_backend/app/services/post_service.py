from ..core.database import supabase

class PostService:
    
    @staticmethod
    async def update_user_post_count(user_id: str, increment: bool = True):
        """Update user's post count"""
        if increment:
            supabase.table("users") \
                .update({"post_count": supabase.raw("post_count + 1")}) \
                .eq("id", user_id) \
                .execute()
        else:
            supabase.table("users") \
                .update({"post_count": supabase.raw("GREATEST(post_count - 1, 0)")}) \
                .eq("id", user_id) \
                .execute()
    
    @staticmethod
    async def get_trending_posts(limit: int = 10):
        """Get trending posts by heat score"""
        result = supabase.table("posts") \
            .select("*") \
            .eq("is_deleted", False) \
            .order("heat_score", desc=True) \
            .limit(limit) \
            .execute()
        return result.data if result.data else []