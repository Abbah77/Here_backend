from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import List, Optional
from datetime import datetime, timedelta
import uuid
import math
import random

from ...core.database import supabase
from ...core.config import settings
from ...models.user import UserInDB
from ...services.user_service import UserService
from ...services.post_service import PostService
from ...schemas.post import (
    PostCreate, PostResponse, PostUpdate,
    CommentCreate, CommentResponse,
    FeedResponse
)
from ..endpoints.auth import get_current_user_dependency

router = APIRouter(prefix="/feed", tags=["feed"])

# ============= HEAT SCORE ALGORITHM =============

class HeatScoreCalculator:
    """
    Calculates trending heat score for posts
    Formula: (likes + comments*2 + shares*3) * time_decay * velocity_boost
    """
    
    @staticmethod
    def calculate(
        like_count: int,
        comment_count: int,
        share_count: int,
        created_at: str,
        recent_engagement: int = 0,
        decay_constant: float = 0.5
    ) -> float:
        """
        Calculate heat score with:
        - Engagement weight: likes (1x), comments (2x), shares (3x)
        - Time decay: exponential decay
        - Velocity boost: recent engagement gets higher score
        """
        
        # Parse created_at
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
        
        # Base engagement score
        base_score = like_count + (comment_count * 2) + (share_count * 3)
        
        # Time decay (exponential)
        hours_age = (datetime.utcnow() - created_at).total_seconds() / 3600
        time_decay = math.exp(-decay_constant * hours_age / 24)  # Decay over days
        
        # Velocity boost (recent engagement matters more)
        velocity_boost = 1.0 + (min(recent_engagement, 100) / 100.0)
        
        # Final heat score
        heat_score = base_score * time_decay * velocity_boost
        
        return round(heat_score, 2)
    
    @staticmethod
    def calculate_trending_score(post_data: dict) -> float:
        """Calculate trending score for a post"""
        
        return HeatScoreCalculator.calculate(
            like_count=post_data.get('like_count', 0),
            comment_count=post_data.get('comment_count', 0),
            share_count=post_data.get('share_count', 0),
            created_at=post_data.get('created_at', datetime.utcnow().isoformat()),
            recent_engagement=post_data.get('like_count', 0) // 10  # Simplified
        )

# ============= POST OPERATIONS =============

@router.post("/posts", response_model=PostResponse, status_code=status.HTTP_201_CREATED)
async def create_post(
    *,
    post_in: PostCreate,
    current_user: UserInDB = Depends(get_current_user_dependency)
):
    """Create a new post"""
    
    post_data = {
        "id": str(uuid.uuid4()),
        "author_id": current_user.id,
        "author_name": current_user.full_name,
        "author_username": current_user.username,
        "author_profile_pic": current_user.profile_pic_url,
        "text": post_in.text,
        "media_url": post_in.media_url,
        "media_type": post_in.media_type,
        "like_count": 0,
        "comment_count": 0,
        "share_count": 0,
        "heat_score": 0.0,
        "is_deleted": False,
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat()
    }
    
    # Insert into Supabase
    result = supabase.table("posts").insert(post_data).execute()
    
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create post"
        )
    
    post = result.data[0]
    
    # Update user post count
    await PostService.update_user_post_count(current_user.id, increment=True)
    
    # Calculate initial heat score
    await update_post_heat_score(post['id'])
    
    return post

@router.get("/posts/{post_id}", response_model=PostResponse)
async def get_post(
    post_id: str,
    current_user: UserInDB = Depends(get_current_user_dependency)
):
    """Get a specific post"""
    
    result = supabase.table("posts") \
        .select("*") \
        .eq("id", post_id) \
        .eq("is_deleted", False) \
        .execute()
    
    if not result.data:
        raise HTTPException(status_code=404, detail="Post not found")
    
    post = result.data[0]
    
    # Check if current user liked this post
    like_result = supabase.table("post_likes") \
        .select("*") \
        .eq("post_id", post_id) \
        .eq("user_id", current_user.id) \
        .execute()
    
    post['is_liked'] = len(like_result.data) > 0
    
    return post

@router.put("/posts/{post_id}", response_model=PostResponse)
async def update_post(
    post_id: str,
    post_in: PostUpdate,
    current_user: UserInDB = Depends(get_current_user_dependency)
):
    """Update a post (only author)"""
    
    # Check if post exists and user is author
    result = supabase.table("posts") \
        .select("*") \
        .eq("id", post_id) \
        .eq("is_deleted", False) \
        .execute()
    
    if not result.data:
        raise HTTPException(status_code=404, detail="Post not found")
    
    post = result.data[0]
    
    if post['author_id'] != current_user.id:
        raise HTTPException(status_code=403, detail="Can only update own posts")
    
    # Update post
    update_data = {
        "updated_at": datetime.utcnow().isoformat()
    }
    if post_in.text is not None:
        update_data["text"] = post_in.text
    
    result = supabase.table("posts") \
        .update(update_data) \
        .eq("id", post_id) \
        .execute()
    
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update post"
        )
    
    return result.data[0]

@router.delete("/posts/{post_id}")
async def delete_post(
    post_id: str,
    current_user: UserInDB = Depends(get_current_user_dependency)
):
    """Delete a post (soft delete)"""
    
    # Check if post exists and user is author
    result = supabase.table("posts") \
        .select("*") \
        .eq("id", post_id) \
        .eq("is_deleted", False) \
        .execute()
    
    if not result.data:
        raise HTTPException(status_code=404, detail="Post not found")
    
    post = result.data[0]
    
    if post['author_id'] != current_user.id:
        raise HTTPException(status_code=403, detail="Can only delete own posts")
    
    # Soft delete
    supabase.table("posts") \
        .update({"is_deleted": True, "updated_at": datetime.utcnow().isoformat()}) \
        .eq("id", post_id) \
        .execute()
    
    # Update user post count
    await PostService.update_user_post_count(current_user.id, increment=False)
    
    return {"status": "deleted"}

# ============= FEED OPERATIONS =============

@router.get("", response_model=FeedResponse)
async def get_feed(
    current_user: UserInDB = Depends(get_current_user_dependency),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    sort_by: str = Query("heat", regex="^(heat|latest|trending)$")
):
    """Get personalized feed with heat score sorting"""
    
    offset = (page - 1) * limit
    
    # Get users that current user follows
    following_result = supabase.table("follows") \
        .select("following_id") \
        .eq("follower_id", current_user.id) \
        .execute()
    
    followed_user_ids = [item['following_id'] for item in following_result.data]
    
    # Include own posts and followed users
    user_ids = [current_user.id] + followed_user_ids
    
    # For discovery, include some posts from other users (20% of feed)
    discovery_count = limit // 5
    
    # Build query for followed users' posts
    query = supabase.table("posts") \
        .select("*") \
        .eq("is_deleted", False) \
        .in_("author_id", user_ids)
    
    # Apply sorting
    if sort_by == "heat":
        query = query.order("heat_score", desc=True)
    elif sort_by == "trending":
        query = query.order("heat_score", desc=True)
    else:  # latest
        query = query.order("created_at", desc=True)
    
    # Get posts
    posts_result = query.range(offset, offset + limit - discovery_count - 1).execute()
    posts = posts_result.data if posts_result.data else []
    
    # Get discovery posts
    discovery_result = supabase.table("posts") \
        .select("*") \
        .eq("is_deleted", False) \
        .not_.in_("author_id", user_ids) \
        .order("created_at", desc=True) \
        .limit(discovery_count) \
        .execute()
    
    discovery_posts = discovery_result.data if discovery_result.data else []
    
    # Combine posts
    all_posts = posts + discovery_posts
    
    # Get total count
    count_result = supabase.table("posts") \
        .select("*", count="exact") \
        .eq("is_deleted", False) \
        .in_("author_id", user_ids) \
        .execute()
    
    total = count_result.count if hasattr(count_result, 'count') else 0
    
    # Check which posts the user liked
    if all_posts:
        post_ids = [p['id'] for p in all_posts]
        likes_result = supabase.table("post_likes") \
            .select("post_id") \
            .eq("user_id", current_user.id) \
            .in_("post_id", post_ids) \
            .execute()
        
        liked_post_ids = {item['post_id'] for item in likes_result.data} if likes_result.data else set()
        
        for post in all_posts:
            post['is_liked'] = post['id'] in liked_post_ids
    
    return FeedResponse(
        posts=all_posts,
        total=total,
        page=page,
        limit=limit,
        has_more=(offset + len(all_posts)) < total
    )

@router.get("/trending", response_model=List[PostResponse])
async def get_trending_posts(
    current_user: UserInDB = Depends(get_current_user_dependency),
    limit: int = Query(10, ge=1, le=50)
):
    """Get trending posts (highest heat score in last 7 days)"""
    
    week_ago = (datetime.utcnow() - timedelta(days=7)).isoformat()
    
    result = supabase.table("posts") \
        .select("*") \
        .eq("is_deleted", False) \
        .gte("created_at", week_ago) \
        .order("heat_score", desc=True) \
        .limit(limit) \
        .execute()
    
    posts = result.data if result.data else []
    
    # Check which posts the user liked
    if posts:
        post_ids = [p['id'] for p in posts]
        likes_result = supabase.table("post_likes") \
            .select("post_id") \
            .eq("user_id", current_user.id) \
            .in_("post_id", post_ids) \
            .execute()
        
        liked_post_ids = {item['post_id'] for item in likes_result.data} if likes_result.data else set()
        
        for post in posts:
            post['is_liked'] = post['id'] in liked_post_ids
    
    return posts

@router.get("/user/{user_id}", response_model=List[PostResponse])
async def get_user_posts(
    user_id: str,
    current_user: UserInDB = Depends(get_current_user_dependency),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100)
):
    """Get posts from a specific user"""
    
    offset = (page - 1) * limit
    
    result = supabase.table("posts") \
        .select("*") \
        .eq("author_id", user_id) \
        .eq("is_deleted", False) \
        .order("created_at", desc=True) \
        .range(offset, offset + limit - 1) \
        .execute()
    
    posts = result.data if result.data else []
    
    # Check which posts the current user liked
    if posts:
        post_ids = [p['id'] for p in posts]
        likes_result = supabase.table("post_likes") \
            .select("post_id") \
            .eq("user_id", current_user.id) \
            .in_("post_id", post_ids) \
            .execute()
        
        liked_post_ids = {item['post_id'] for item in likes_result.data} if likes_result.data else set()
        
        for post in posts:
            post['is_liked'] = post['id'] in liked_post_ids
    
    return posts

# ============= LIKE OPERATIONS =============

@router.post("/posts/{post_id}/like")
async def like_post(
    post_id: str,
    current_user: UserInDB = Depends(get_current_user_dependency)
):
    """Like a post"""
    
    # Check if already liked
    existing = supabase.table("post_likes") \
        .select("*") \
        .eq("post_id", post_id) \
        .eq("user_id", current_user.id) \
        .execute()
    
    if existing.data:
        raise HTTPException(status_code=400, detail="Post already liked")
    
    # Create like
    like_data = {
        "post_id": post_id,
        "user_id": current_user.id,
        "created_at": datetime.utcnow().isoformat()
    }
    
    supabase.table("post_likes").insert(like_data).execute()
    
    # Update post like count
    supabase.table("posts") \
        .update({"like_count": supabase.raw("like_count + 1")}) \
        .eq("id", post_id) \
        .execute()
    
    # Update heat score
    await update_post_heat_score(post_id)
    
    # Get post author for notification
    post_result = supabase.table("posts") \
        .select("author_id") \
        .eq("id", post_id) \
        .execute()
    
    if post_result.data and post_result.data[0]['author_id'] != current_user.id:
        # TODO: Send notification to post author
        pass
    
    return {"status": "liked"}

@router.delete("/posts/{post_id}/like")
async def unlike_post(
    post_id: str,
    current_user: UserInDB = Depends(get_current_user_dependency)
):
    """Unlike a post"""
    
    # Delete like
    result = supabase.table("post_likes") \
        .delete() \
        .eq("post_id", post_id) \
        .eq("user_id", current_user.id) \
        .execute()
    
    if not result.data:
        raise HTTPException(status_code=404, detail="Like not found")
    
    # Update post like count
    supabase.table("posts") \
        .update({"like_count": supabase.raw("GREATEST(like_count - 1, 0)")}) \
        .eq("id", post_id) \
        .execute()
    
    # Update heat score
    await update_post_heat_score(post_id)
    
    return {"status": "unliked"}

@router.get("/posts/{post_id}/likes", response_model=List[dict])
async def get_post_likes(
    post_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100)
):
    """Get users who liked a post"""
    
    result = supabase.table("post_likes") \
        .select("user_id, created_at, users!post_likes_user_id_fkey(full_name, username, profile_pic_url)") \
        .eq("post_id", post_id) \
        .range(skip, skip + limit - 1) \
        .execute()
    
    likes = []
    if result.data:
        for item in result.data:
            user = item.get('users', {})
            likes.append({
                "user_id": item['user_id'],
                "user_name": user.get('full_name', ''),
                "user_username": user.get('username', ''),
                "user_profile_pic": user.get('profile_pic_url'),
                "created_at": item['created_at']
            })
    
    return likes

# ============= COMMENT OPERATIONS =============

@router.post("/posts/{post_id}/comments", response_model=CommentResponse)
async def add_comment(
    post_id: str,
    comment_in: CommentCreate,
    current_user: UserInDB = Depends(get_current_user_dependency)
):
    """Add a comment to a post"""
    
    comment_data = {
        "id": str(uuid.uuid4()),
        "post_id": post_id,
        "user_id": current_user.id,
        "user_name": current_user.full_name,
        "user_profile_pic": current_user.profile_pic_url,
        "text": comment_in.text,
        "like_count": 0,
        "created_at": datetime.utcnow().isoformat()
    }
    
    result = supabase.table("comments").insert(comment_data).execute()
    
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to add comment"
        )
    
    # Update post comment count
    supabase.table("posts") \
        .update({"comment_count": supabase.raw("comment_count + 1")}) \
        .eq("id", post_id) \
        .execute()
    
    # Update heat score
    await update_post_heat_score(post_id)
    
    return result.data[0]

@router.get("/posts/{post_id}/comments", response_model=List[CommentResponse])
async def get_post_comments(
    post_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100)
):
    """Get comments for a post"""
    
    result = supabase.table("comments") \
        .select("*") \
        .eq("post_id", post_id) \
        .order("created_at", desc=True) \
        .range(skip, skip + limit - 1) \
        .execute()
    
    return result.data if result.data else []

@router.delete("/comments/{comment_id}")
async def delete_comment(
    comment_id: str,
    current_user: UserInDB = Depends(get_current_user_dependency)
):
    """Delete a comment"""
    
    # Get comment
    comment_result = supabase.table("comments") \
        .select("*") \
        .eq("id", comment_id) \
        .execute()
    
    if not comment_result.data:
        raise HTTPException(status_code=404, detail="Comment not found")
    
    comment = comment_result.data[0]
    
    # Get post to check author
    post_result = supabase.table("posts") \
        .select("author_id") \
        .eq("id", comment['post_id']) \
        .execute()
    
    # Only comment author or post author can delete
    if comment['user_id'] != current_user.id and \
       (not post_result.data or post_result.data[0]['author_id'] != current_user.id):
        raise HTTPException(status_code=403, detail="Not authorized to delete this comment")
    
    # Delete comment
    supabase.table("comments") \
        .delete() \
        .eq("id", comment_id) \
        .execute()
    
    # Update post comment count
    supabase.table("posts") \
        .update({"comment_count": supabase.raw("GREATEST(comment_count - 1, 0)")}) \
        .eq("id", comment['post_id']) \
        .execute()
    
    # Update heat score
    await update_post_heat_score(comment['post_id'])
    
    return {"status": "deleted"}

# ============= SHARE OPERATIONS =============

@router.post("/posts/{post_id}/share")
async def share_post(
    post_id: str,
    current_user: UserInDB = Depends(get_current_user_dependency)
):
    """Share a post (increment share count)"""
    
    # Check if post exists
    post_result = supabase.table("posts") \
        .select("*") \
        .eq("id", post_id) \
        .eq("is_deleted", False) \
        .execute()
    
    if not post_result.data:
        raise HTTPException(status_code=404, detail="Post not found")
    
    # Increment share count
    supabase.table("posts") \
        .update({"share_count": supabase.raw("share_count + 1")}) \
        .eq("id", post_id) \
        .execute()
    
    # Update heat score
    await update_post_heat_score(post_id)
    
    # TODO: Create a shared post entry
    
    return {"status": "shared"}

# ============= HEAT SCORE MANAGEMENT =============

async def update_post_heat_score(post_id: str) -> None:
    """Update heat score for a post"""
    
    # Get post data
    result = supabase.table("posts") \
        .select("*") \
        .eq("id", post_id) \
        .execute()
    
    if not result.data:
        return
    
    post = result.data[0]
    
    # Calculate new heat score
    new_score = HeatScoreCalculator.calculate_trending_score(post)
    
    # Update if changed significantly
    if abs(post.get('heat_score', 0) - new_score) > 0.1:
        supabase.table("posts") \
            .update({"heat_score": new_score}) \
            .eq("id", post_id) \
            .execute()

@router.post("/admin/recalculate-heat-scores")
async def recalculate_all_heat_scores(
    current_user: UserInDB = Depends(get_current_user_dependency)
):
    """Admin endpoint to recalculate all heat scores"""
    
    # Check if admin (you can implement proper admin check)
    if not current_user.is_verified:  # Simplified
        raise HTTPException(status_code=403, detail="Admin access required")
    
    # Get all posts
    result = supabase.table("posts") \
        .select("*") \
        .eq("is_deleted", False) \
        .execute()
    
    posts = result.data if result.data else []
    
    # Update each post's heat score
    for post in posts:
        new_score = HeatScoreCalculator.calculate_trending_score(post)
        supabase.table("posts") \
            .update({"heat_score": new_score}) \
            .eq("id", post['id']) \
            .execute()
    
    return {"status": f"Updated {len(posts)} posts"}

# ============= FEED CUSTOMIZATION =============

@router.get("/recommendations")
async def get_recommended_posts(
    current_user: UserInDB = Depends(get_current_user_dependency),
    limit: int = Query(10, ge=1, le=50)
):
    """
    AI-powered post recommendations based on user interests
    """
    
    # TODO: Implement ML-based recommendations using AI service
    # For now, return random popular posts
    
    result = supabase.table("posts") \
        .select("*") \
        .eq("is_deleted", False) \
        .order("heat_score", desc=True) \
        .limit(limit * 3) \
        .execute()
    
    posts = result.data if result.data else []
    
    # Randomize
    random.shuffle(posts)
    
    # Take first 'limit' posts
    posts = posts[:limit]
    
    # Check which posts the user liked
    if posts:
        post_ids = [p['id'] for p in posts]
        likes_result = supabase.table("post_likes") \
            .select("post_id") \
            .eq("user_id", current_user.id) \
            .in_("post_id", post_ids) \
            .execute()
        
        liked_post_ids = {item['post_id'] for item in likes_result.data} if likes_result.data else set()
        
        for post in posts:
            post['is_liked'] = post['id'] in liked_post_ids
    
    return posts

# ============= ANALYTICS =============

@router.get("/analytics/engagement")
async def get_engagement_analytics(
    current_user: UserInDB = Depends(get_current_user_dependency),
    days: int = Query(7, ge=1, le=30)
):
    """Get engagement analytics for user's posts"""
    
    start_date = (datetime.utcnow() - timedelta(days=days)).isoformat()
    
    # Get user's posts in date range
    result = supabase.table("posts") \
        .select("*") \
        .eq("author_id", current_user.id) \
        .eq("is_deleted", False) \
        .gte("created_at", start_date) \
        .execute()
    
    posts = result.data if result.data else []
    
    total_likes = sum(p.get('like_count', 0) for p in posts)
    total_comments = sum(p.get('comment_count', 0) for p in posts)
    total_shares = sum(p.get('share_count', 0) for p in posts)
    
    return {
        "total_posts": len(posts),
        "total_likes": total_likes,
        "total_comments": total_comments,
        "total_shares": total_shares,
        "avg_heat_score": sum(p.get('heat_score', 0) for p in posts) / len(posts) if posts else 0,
        "engagement_rate": (total_likes + total_comments + total_shares) / len(posts) if posts else 0
    }