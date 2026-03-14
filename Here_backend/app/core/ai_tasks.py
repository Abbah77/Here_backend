import asyncio
import logging
from datetime import datetime, timedelta
from ..services.ai_service import ai_service
from ..core.database import supabase  # Import Supabase client

logger = logging.getLogger(__name__)

async def train_recommendation_models():
    """Background task to train AI models using Supabase data"""
    
    logger.info("Starting AI model training...")
    
    try:
        # Generate user embeddings - ai_service needs to be updated to work with Supabase
        start = datetime.utcnow()
        await ai_service.generate_user_embeddings_supabase()  # We'll need to update ai_service
        user_time = (datetime.utcnow() - start).total_seconds()
        
        # Generate post embeddings
        start = datetime.utcnow()
        await ai_service.generate_post_embeddings_supabase()  # We'll need to update ai_service
        post_time = (datetime.utcnow() - start).total_seconds()
        
        logger.info(f"AI training complete - Users: {user_time:.2f}s, Posts: {post_time:.2f}s")
        
    except Exception as e:
        logger.error(f"AI training failed: {e}")

async def schedule_ai_training():
    """Schedule periodic AI model training"""
    while True:
        await asyncio.sleep(3600 * 24)  # Train once per day
        asyncio.create_task(train_recommendation_models())

# ============= Helper functions for AI service with Supabase =============

async def fetch_all_users_for_ai():
    """Fetch all users from Supabase for AI training"""
    try:
        result = supabase.table("users") \
            .select("id, email, username, full_name, bio, follower_count, following_count, post_count, heat_score, is_verified, created_at") \
            .eq("is_active", True) \
            .execute()
        
        return result.data if result.data else []
    except Exception as e:
        logger.error(f"Failed to fetch users for AI: {e}")
        return []

async def fetch_all_posts_for_ai():
    """Fetch all posts from Supabase for AI training"""
    try:
        result = supabase.table("posts") \
            .select("id, author_id, text, media_url, media_type, like_count, comment_count, share_count, heat_score, created_at") \
            .eq("is_deleted", False) \
            .execute()
        
        return result.data if result.data else []
    except Exception as e:
        logger.error(f"Failed to fetch posts for AI: {e}")
        return []

async def fetch_user_interactions(user_id: str):
    """Fetch user interactions (likes, comments) for AI training"""
    try:
        # Get posts user liked
        likes = supabase.table("post_likes") \
            .select("post_id, created_at") \
            .eq("user_id", user_id) \
            .execute()
        
        # Get comments user made
        comments = supabase.table("comments") \
            .select("post_id, text, created_at") \
            .eq("user_id", user_id) \
            .execute()
        
        return {
            "likes": likes.data if likes.data else [],
            "comments": comments.data if comments.data else []
        }
    except Exception as e:
        logger.error(f"Failed to fetch interactions for user {user_id}: {e}")
        return {"likes": [], "comments": []}

# Add to main.py startup
# asyncio.create_task(schedule_ai_training())