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

# ============= SQLAlchemy (Optional - if you want to keep for ORM) =============
# Note: You can keep SQLAlchemy if you prefer it, but it will connect to Supabase's PostgreSQL

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import NullPool

# SQLAlchemy engine using Supabase PostgreSQL connection
# Extract PostgreSQL URL from Supabase URL
def get_postgres_url() -> str:
    """Convert Supabase URL to PostgreSQL connection string"""
    if settings.SUPABASE_URL:
        # Format: postgresql://postgres:[PASSWORD]@db.[PROJECT_REF].supabase.co:5432/postgres
        project_ref = settings.SUPABASE_URL.replace("https://", "").split(".")[0]
        # You'll need to get your PostgreSQL password from Supabase dashboard
        return f"postgresql://postgres:{settings.SUPABASE_POSTGRES_PASSWORD}@db.{project_ref}.supabase.co:5432/postgres"
    return settings.DATABASE_URL  # Fallback to original

# Optional: Keep SQLAlchemy if you want to use it alongside Supabase
if settings.DATABASE_URL or settings.SUPABASE_URL:
    # Create SQLAlchemy engine (optional)
    sqlalchemy_engine = create_engine(
        get_postgres_url() if settings.SUPABASE_URL else settings.DATABASE_URL,
        pool_pre_ping=True,
        pool_size=20,
        max_overflow=0,
        echo=settings.DEBUG
    )
    
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=sqlalchemy_engine)
    Base = declarative_base()
    
    def get_sqlalchemy_db() -> Generator[Session, None, None]:
        """Optional: Keep SQLAlchemy session if needed"""
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()