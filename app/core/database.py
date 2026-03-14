from typing import Generator, Optional
from supabase import create_client, Client
from .config import settings
import redis.asyncio as redis
from contextlib import contextmanager

# ============= SUPABASE SETUP =============

# Supabase client (for backend operations - uses service key)
supabase: Client = create_client(
    settings.SUPABASE_URL,
    settings.SUPABASE_SERVICE_KEY
)

# Supabase client for public operations (uses anon key)
supabase_public: Client = create_client(
    settings.SUPABASE_URL,
    settings.SUPABASE_ANON_KEY
)

# ============= REDIS SETUP (optional) =============

# Redis client (if you still need it - otherwise you can remove)
redis_client = None
if settings.REDIS_URL:
    redis_client = redis.from_url(
        settings.REDIS_URL,
        encoding="utf-8",
        decode_responses=True
    )

# ============= DEPENDENCIES =============

def get_db() -> Client:
    """
    Dependency to get Supabase client with service role
    Use this for backend operations (admin-level access)
    """
    return supabase

def get_public_db() -> Client:
    """
    Dependency to get Supabase client with anon key
    Use this for public operations (RLS will apply)
    """
    return supabase_public

async def get_redis() -> Optional[redis.Redis]:
    """
    Dependency to get Redis client (if configured)
    """
    return redis_client

# ============= HEALTH CHECK =============

async def check_supabase_connection() -> bool:
    """
    Check if Supabase connection is working
    """
    try:
        # Try a simple query to check connection
        result = supabase.table("_dummy").select("*").limit(1).execute()
        return True
    except Exception as e:
        print(f"Supabase connection error: {e}")
        return False
