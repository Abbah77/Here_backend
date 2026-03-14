# Replace methods that use SQLAlchemy with Supabase versions

async def generate_user_embeddings_supabase(self):
    """Generate embeddings for users using Supabase data"""
    
    # Fetch users
    users = await fetch_all_users_for_ai()  # Use helper from ai_tasks
    
    for user_data in users:
        # Fetch user interactions
        interactions = await fetch_user_interactions(user_data['id'])
        
        # Rest of your embedding logic stays the same
        # but use the data from Supabase instead of SQLAlchemy objects
        
        # Create embedding
        user_embedding = self._create_user_embedding_from_data(user_data, interactions)
        self.user_embeddings[user_data['id']] = user_embedding
        
        # Optionally store embedding back to Supabase
        supabase.table("users") \
            .update({"embedding": user_embedding.tolist()}) \
            .eq("id", user_data['id']) \
            .execute()
    
    self._save_models()

async def generate_post_embeddings_supabase(self):
    """Generate embeddings for posts using Supabase data"""
    
    # Fetch posts
    posts = await fetch_all_posts_for_ai()
    
    for post_data in posts:
        # Create embedding
        post_embedding = self._create_post_embedding_from_data(post_data)
        self.post_embeddings[post_data['id']] = post_embedding
    
    self._save_models()