import numpy as np
import pandas as pd
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
import asyncio
import logging
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.cluster import KMeans
import joblib
import os
import json
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func, desc
import hashlib
import pickle

from ..core.config import settings
from ..models.user import User
from ..models.post import Post, PostLike, Comment
from ..models.message import Message
from ..database import SessionLocal

logger = logging.getLogger(__name__)

class AIRecommender:
    """
    AI-powered recommendation system for users and content
    Uses collaborative filtering and content-based approaches
    """
    
    def __init__(self):
        self.model_path = settings.ML_MODEL_PATH
        self.vectorizer = TfidfVectorizer(max_features=1000, stop_words='english')
        self.user_embeddings = {}
        self.post_embeddings = {}
        self.similarity_matrix = None
        
        # Load existing models if available
        self._load_models()
    
    def _load_models(self):
        """Load pre-trained models from disk"""
        try:
            if os.path.exists(f"{self.model_path}/user_embeddings.pkl"):
                with open(f"{self.model_path}/user_embeddings.pkl", 'rb') as f:
                    self.user_embeddings = pickle.load(f)
            
            if os.path.exists(f"{self.model_path}/post_embeddings.pkl"):
                with open(f"{self.model_path}/post_embeddings.pkl", 'rb') as f:
                    self.post_embeddings = pickle.load(f)
            
            if os.path.exists(f"{self.model_path}/vectorizer.pkl"):
                with open(f"{self.model_path}/vectorizer.pkl", 'rb') as f:
                    self.vectorizer = pickle.load(f)
                    
            logger.info("Loaded AI models from disk")
        except Exception as e:
            logger.error(f"Failed to load models: {e}")
    
    def _save_models(self):
        """Save trained models to disk"""
        try:
            os.makedirs(self.model_path, exist_ok=True)
            
            with open(f"{self.model_path}/user_embeddings.pkl", 'wb') as f:
                pickle.dump(self.user_embeddings, f)
            
            with open(f"{self.model_path}/post_embeddings.pkl", 'wb') as f:
                pickle.dump(self.post_embeddings, f)
            
            with open(f"{self.model_path}/vectorizer.pkl", 'wb') as f:
                pickle.dump(self.vectorizer, f)
                
            logger.info("Saved AI models to disk")
        except Exception as e:
            logger.error(f"Failed to save models: {e}")
    
    # ============= USER EMBEDDINGS =============
    
    async def generate_user_embeddings(self, db: Session) -> Dict[str, np.ndarray]:
        """
        Generate embeddings for users based on:
        - Their posts content
        - Their interactions (likes, comments)
        - Who they follow
        """
        users = db.query(User).all()
        
        for user in users:
            # Get user's posts
            posts = db.query(Post).filter(Post.author_id == user.id).all()
            post_texts = [p.text for p in posts if p.text]
            
            # Get user's liked posts
            liked_posts = db.query(Post).join(PostLike).filter(
                PostLike.user_id == user.id
            ).all()
            liked_texts = [p.text for p in liked_posts if p.text]
            
            # Get user's comments
            comments = db.query(Comment).filter(Comment.user_id == user.id).all()
            comment_texts = [c.text for c in comments]
            
            # Combine all text
            all_texts = post_texts + liked_texts + comment_texts
            
            if all_texts:
                # Create TF-IDF vectors
                text_matrix = self.vectorizer.fit_transform(all_texts)
                user_embedding = text_matrix.mean(axis=0).A1
            else:
                # Fallback for users with no content
                user_embedding = np.zeros(self.vectorizer.max_features)
            
            # Add metadata features
            metadata_features = np.array([
                user.follower_count / 1000,  # Normalized followers
                user.following_count / 1000,  # Normalized following
                user.post_count / 100,        # Normalized posts
                user.heat_score / 100,        # Normalized heat
                1 if user.is_verified else 0   # Verified status
            ])
            
            # Combine text and metadata
            full_embedding = np.concatenate([user_embedding, metadata_features])
            self.user_embeddings[user.id] = full_embedding
        
        self._save_models()
        return self.user_embeddings
    
    async def find_similar_users(
        self,
        user_id: str,
        db: Session,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Find users similar to a given user"""
        
        if user_id not in self.user_embeddings:
            await self.generate_user_embeddings(db)
        
        target_embedding = self.user_embeddings.get(user_id)
        if target_embedding is None:
            return []
        
        similarities = []
        for uid, embedding in self.user_embeddings.items():
            if uid != user_id:
                # Calculate cosine similarity
                sim = cosine_similarity(
                    target_embedding.reshape(1, -1),
                    embedding.reshape(1, -1)
                )[0][0]
                
                user = db.query(User).filter(User.id == uid).first()
                if user:
                    similarities.append({
                        "user_id": uid,
                        "username": user.username,
                        "full_name": user.full_name,
                        "profile_pic_url": user.profile_pic_url,
                        "similarity_score": float(sim),
                        "mutual_followers": await self._count_mutual_followers(user_id, uid, db)
                    })
        
        # Sort by similarity and return top
        similarities.sort(key=lambda x: x['similarity_score'], reverse=True)
        return similarities[:limit]
    
    async def _count_mutual_followers(self, user_id1: str, user_id2: str, db: Session) -> int:
        """Count mutual followers between two users"""
        # This would query the follows table
        # Simplified for now
        return 0
    
    # ============= POST RECOMMENDATIONS =============
    
    async def generate_post_embeddings(self, db: Session) -> Dict[str, np.ndarray]:
        """Generate embeddings for posts based on content and engagement"""
        
        posts = db.query(Post).filter(Post.is_deleted == False).all()
        
        for post in posts:
            features = []
            
            # Text content (if available)
            if post.text:
                text_vector = self.vectorizer.fit_transform([post.text]).toarray()[0]
                features.append(text_vector)
            
            # Engagement features
            engagement_features = np.array([
                post.like_count / 1000,      # Normalized likes
                post.comment_count / 100,     # Normalized comments
                post.share_count / 100,       # Normalized shares
                post.heat_score / 100,        # Heat score
                await self._get_post_age_factor(post.created_at)  # Time decay
            ])
            features.append(engagement_features)
            
            # Author influence
            author = db.query(User).filter(User.id == post.author_id).first()
            if author:
                author_features = np.array([
                    author.follower_count / 1000,
                    author.heat_score / 100,
                    1 if author.is_verified else 0
                ])
                features.append(author_features)
            
            # Combine all features
            if features:
                post_embedding = np.concatenate(features)
                self.post_embeddings[post.id] = post_embedding
        
        self._save_models()
        return self.post_embeddings
    
    async def _get_post_age_factor(self, created_at: datetime) -> float:
        """Calculate time decay factor for post (newer = higher)"""
        hours_age = (datetime.utcnow() - created_at).total_seconds() / 3600
        return np.exp(-hours_age / 72)  # Decay over 3 days
    
    async def recommend_posts_for_user(
        self,
        user_id: str,
        db: Session,
        limit: int = 20,
        include_reasons: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Personalized post recommendations using:
        - Collaborative filtering (users like you liked these)
        - Content-based (posts similar to your interests)
        - Trending (high heat score)
        - From followed users (but not too many)
        """
        
        # Get user's interaction history
        liked_posts = db.query(PostLike).filter(PostLike.user_id == user_id).all()
        liked_post_ids = [lp.post_id for lp in liked_posts]
        
        # Get user's comments
        commented_posts = db.query(Comment).filter(Comment.user_id == user_id).all()
        commented_post_ids = [cp.post_id for cp in commented_posts]
        
        # Combine interacted posts
        interacted_posts = set(liked_post_ids + commented_post_ids)
        
        # Get posts from followed users (40% of recommendations)
        followed_users = [f.following_id for f in db.query(User).filter(User.id == user_id).first().following]
        followed_posts = db.query(Post).filter(
            Post.author_id.in_(followed_users),
            Post.is_deleted == False,
            ~Post.id.in_(interacted_posts)  # Exclude already interacted
        ).order_by(desc(Post.heat_score)).limit(int(limit * 0.4)).all()
        
        # Collaborative filtering (30%)
        similar_users = await self.find_similar_users(user_id, db, limit=10)
        similar_user_ids = [su['user_id'] for su in similar_users]
        
        collab_posts = db.query(Post).filter(
            Post.author_id.in_(similar_user_ids),
            Post.is_deleted == False,
            ~Post.id.in_(interacted_posts)
        ).order_by(desc(Post.heat_score)).limit(int(limit * 0.3)).all()
        
        # Content-based (20%)
        # Find posts similar to user's past interactions
        content_posts = await self._content_based_recommendations(
            user_id, list(interacted_posts), db, int(limit * 0.2)
        )
        
        # Trending/Discovery (10%)
        trending_posts = db.query(Post).filter(
            Post.is_deleted == False,
            ~Post.id.in_(interacted_posts)
        ).order_by(desc(Post.heat_score)).limit(int(limit * 0.1)).all()
        
        # Combine and deduplicate
        all_posts = []
        seen_ids = set()
        
        for post_list in [followed_posts, collab_posts, content_posts, trending_posts]:
            for post in post_list:
                if post.id not in seen_ids:
                    seen_ids.add(post.id)
                    
                    recommendation = {
                        "post": post,
                        "reason": self._get_recommendation_reason(post, user_id, db)
                    }
                    all_posts.append(recommendation)
        
        # Sort by combined score
        all_posts.sort(
            key=lambda x: self._calculate_recommendation_score(x['post'], user_id, db),
            reverse=True
        )
        
        return all_posts[:limit]
    
    async def _content_based_recommendations(
        self,
        user_id: str,
        interacted_posts: List[str],
        db: Session,
        limit: int
    ) -> List[Post]:
        """Find posts similar to user's past interactions"""
        
        if not interacted_posts or not self.post_embeddings:
            return []
        
        # Get embeddings for interacted posts
        interacted_embeddings = []
        for post_id in interacted_posts:
            if post_id in self.post_embeddings:
                interacted_embeddings.append(self.post_embeddings[post_id])
        
        if not interacted_embeddings:
            return []
        
        # Average embedding of user's interests
        user_interest = np.mean(interacted_embeddings, axis=0)
        
        # Find similar posts
        similar_posts = []
        for post_id, embedding in self.post_embeddings.items():
            if post_id not in interacted_posts:
                sim = cosine_similarity(
                    user_interest.reshape(1, -1),
                    embedding.reshape(1, -1)
                )[0][0]
                
                post = db.query(Post).filter(Post.id == post_id).first()
                if post:
                    similar_posts.append((post, sim))
        
        # Sort by similarity
        similar_posts.sort(key=lambda x: x[1], reverse=True)
        return [p[0] for p in similar_posts[:limit]]
    
    def _get_recommendation_reason(self, post: Post, user_id: str, db: Session) -> str:
        """Generate human-readable reason for recommendation"""
        
        # Check if from followed user
        followed_users = [f.following_id for f in db.query(User).filter(User.id == user_id).first().following]
        if post.author_id in followed_users:
            return f"From {post.author.full_name}, who you follow"
        
        # Check if similar to liked posts
        if post.like_count > 100:
            return "Trending in your network"
        
        # Check if popular
        if post.heat_score > 50:
            return "Popular post you might like"
        
        return "Recommended for you"
    
    def _calculate_recommendation_score(self, post: Post, user_id: str, db: Session) -> float:
        """Calculate combined recommendation score"""
        
        score = post.heat_score * 0.4  # Base heat score
        
        # Boost for followed users
        followed_users = [f.following_id for f in db.query(User).filter(User.id == user_id).first().following]
        if post.author_id in followed_users:
            score *= 1.5
        
        # Boost for recent posts
        age_factor = 1 / (1 + (datetime.utcnow() - post.created_at).days)
        score *= (1 + age_factor)
        
        return score
    
    # ============= TRENDING TOPICS =============
    
    async def extract_trending_topics(
        self,
        db: Session,
        hours: int = 24,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Extract trending topics from recent posts"""
        
        since = datetime.utcnow() - timedelta(hours=hours)
        
        # Get recent posts
        recent_posts = db.query(Post).filter(
            Post.created_at >= since,
            Post.is_deleted == False,
            Post.text != None
        ).all()
        
        # Extract text
        texts = [p.text for p in recent_posts if p.text]
        
        if not texts:
            return []
        
        # Vectorize
        tfidf_matrix = self.vectorizer.fit_transform(texts)
        feature_names = self.vectorizer.get_feature_names_out()
        
        # Sum TF-IDF scores
        topic_scores = np.array(tfidf_matrix.sum(axis=0)).flatten()
        
        # Get top topics
        top_indices = topic_scores.argsort()[-limit:][::-1]
        
        trending_topics = []
        for idx in top_indices:
            if topic_scores[idx] > 0:
                trending_topics.append({
                    "topic": feature_names[idx],
                    "score": float(topic_scores[idx]),
                    "post_count": len([t for t in texts if feature_names[idx] in t.lower()])
                })
        
        return trending_topics
    
    # ============= CONTENT MODERATION =============
    
    async def moderate_content(self, text: str) -> Dict[str, Any]:
        """
        Basic content moderation
        In production, use a service like Google Perspective API or custom ML model
        """
        
        # Simple keyword-based moderation (replace with actual ML model)
        toxic_keywords = ['hate', 'violence', 'abuse', 'harassment', 'spam']
        spam_patterns = ['http://', 'https://', 'www.', 'buy now', 'click here']
        
        text_lower = text.lower()
        
        # Check for toxic content
        toxic_score = 0
        for keyword in toxic_keywords:
            if keyword in text_lower:
                toxic_score += 0.2
        
        # Check for spam
        spam_score = 0
        for pattern in spam_patterns:
            if pattern in text_lower:
                spam_score += 0.15
        
        # Overall safety score
        safety_score = 1.0 - min(toxic_score + spam_score, 1.0)
        
        return {
            "is_safe": safety_score > 0.7,
            "safety_score": safety_score,
            "toxic_score": toxic_score,
            "spam_score": spam_score,
            "flags": {
                "has_toxic_content": toxic_score > 0.3,
                "has_spam": spam_score > 0.3,
                "needs_review": safety_score < 0.7 and safety_score > 0.3
            }
        }
    
    # ============= USER SEGMENTATION =============
    
    async def segment_users(
        self,
        db: Session,
        n_clusters: int = 5
    ) -> Dict[str, int]:
        """Cluster users into segments for targeted features"""
        
        if len(self.user_embeddings) < n_clusters:
            await self.generate_user_embeddings(db)
        
        if not self.user_embeddings:
            return {}
        
        # Prepare data
        user_ids = list(self.user_embeddings.keys())
        embeddings = np.array([self.user_embeddings[uid] for uid in user_ids])
        
        # Cluster
        kmeans = KMeans(n_clusters=n_clusters, random_state=42)
        clusters = kmeans.fit_predict(embeddings)
        
        # Map users to clusters
        user_clusters = {}
        for i, user_id in enumerate(user_ids):
            user_clusters[user_id] = int(clusters[i])
        
        return user_clusters

# ============= AI API ENDPOINTS =============

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

ai_router = APIRouter(prefix="/ai", tags=["ai"])

# Initialize AI service
ai_service = AIRecommender()

class RecommendationRequest(BaseModel):
    user_id: str
    limit: int = 20

class ModerationRequest(BaseModel):
    text: str

@ai_router.post("/recommendations/posts")
async def get_post_recommendations(
    request: RecommendationRequest,
    db: Session = Depends(get_db)
):
    """Get personalized post recommendations"""
    
    recommendations = await ai_service.recommend_posts_for_user(
        user_id=request.user_id,
        db=db,
        limit=request.limit
    )
    
    return {"recommendations": recommendations}

@ai_router.get("/recommendations/users/{user_id}")
async def get_user_recommendations(
    user_id: str,
    db: Session = Depends(get_db),
    limit: int = 10
):
    """Get similar user recommendations"""
    
    similar_users = await ai_service.find_similar_users(
        user_id=user_id,
        db=db,
        limit=limit
    )
    
    return {"similar_users": similar_users}

@ai_router.get("/trending/topics")
async def get_trending_topics(
    db: Session = Depends(get_db),
    hours: int = 24,
    limit: int = 10
):
    """Get currently trending topics"""
    
    topics = await ai_service.extract_trending_topics(
        db=db,
        hours=hours,
        limit=limit
    )
    
    return {"trending_topics": topics}

@ai_router.post("/moderate")
async def moderate_content(
    request: ModerationRequest
):
    """Moderate content for safety"""
    
    result = await ai_service.moderate_content(request.text)
    return result

@ai_router.post("/train")
async def train_models(
    db: Session = Depends(get_db)
):
    """Manually trigger model training"""
    
    await ai_service.generate_user_embeddings(db)
    await ai_service.generate_post_embeddings(db)
    
    return {"status": "training_completed"}

# Add to main.py
# app.include_router(ai_router, prefix=api_prefix)