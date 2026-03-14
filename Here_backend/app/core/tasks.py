import asyncio
import logging
from datetime import datetime, timedelta
from ..database import supabase
from ...api.endpoints.feed import update_post_heat_score

logger = logging.getLogger(__name__)

async def update_all_heat_scores():
    """Background task to update heat scores for all posts using Supabase"""
    
    logger.info("Starting heat score update for all posts")
    
    try:
        # Get all non-deleted posts from Supabase
        result = supabase.table("posts") \
            .select("*") \
            .eq("is_deleted", False) \
            .execute()
        
        posts = result.data if result.data else []
        
        if not posts:
            logger.info("No posts to update")
            return
        
        # Update each post's heat score
        for post in posts:
            await update_post_heat_score(post['id'])
        
        logger.info(f"Updated heat scores for {len(posts)} posts")
        
    except Exception as e:
        logger.error(f"Error updating heat scores: {e}")

async def update_trending_users():
    """Background task to update user heat scores based on engagement"""
    
    logger.info("Starting trending users update")
    
    try:
        # Get all active users
        result = supabase.table("users") \
            .select("id, post_count, follower_count") \
            .eq("is_active", True) \
            .execute()
        
        users = result.data if result.data else []
        
        for user in users:
            # Calculate user heat score based on posts and followers
            user_heat = (user.get('post_count', 0) * 10) + user.get('follower_count', 0)
            
            # Update user heat score
            supabase.table("users") \
                .update({"heat_score": user_heat}) \
                .eq("id", user['id']) \
                .execute()
        
        logger.info(f"Updated heat scores for {len(users)} users")
        
    except Exception as e:
        logger.error(f"Error updating user heat scores: {e}")

async def cleanup_old_data():
    """Background task to clean up old data"""
    
    logger.info("Starting cleanup of old data")
    
    try:
        # Delete old notifications (older than 30 days)
        thirty_days_ago = (datetime.utcnow() - timedelta(days=30)).isoformat()
        
        # You would need a notifications table for this
        # result = supabase.table("notifications") \
        #     .delete() \
        #     .lt("created_at", thirty_days_ago) \
        #     .execute()
        
        logger.info("Cleanup completed")
        
    except Exception as e:
        logger.error(f"Error during cleanup: {e}")

async def schedule_tasks():
    """Schedule all periodic tasks"""
    
    # Task 1: Update heat scores every hour
    while True:
        await asyncio.sleep(3600)  # 1 hour
        try:
            await update_all_heat_scores()
        except Exception as e:
            logger.error(f"Heat score update task failed: {e}")
    
    # Task 2: Update trending users every 6 hours
    # while True:
    #     await asyncio.sleep(21600)  # 6 hours
    #     try:
    #         await update_trending_users()
    #     except Exception as e:
    #         logger.error(f"Trending users update failed: {e}")
    
    # Task 3: Cleanup old data every 24 hours
    # while True:
    #     await asyncio.sleep(86400)  # 24 hours
    #     try:
    #         await cleanup_old_data()
    #     except Exception as e:
    #         logger.error(f"Cleanup task failed: {e}")

# Individual scheduler functions (call these from main.py)

async def schedule_heat_score_updates():
    """Schedule periodic heat score updates (call this from main.py)"""
    while True:
        await asyncio.sleep(3600)  # Run every hour
        asyncio.create_task(update_all_heat_scores())

async def schedule_trending_updates():
    """Schedule periodic trending users updates"""
    while True:
        await asyncio.sleep(21600)  # Run every 6 hours
        asyncio.create_task(update_trending_users())

async def schedule_cleanup():
    """Schedule periodic cleanup"""
    while True:
        await asyncio.sleep(86400)  # Run every 24 hours
        asyncio.create_task(cleanup_old_data())