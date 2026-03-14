import os
from typing import List, Optional
from pydantic_settings import BaseSettings
from pydantic import validator
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseSettings):
    # App
    APP_NAME: str = "Here Backend"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"
    
    # Server - Hugging Face uses PORT env var
    HOST: str = "0.0.0.0"
    PORT: int = int(os.getenv("PORT", "7860"))  # HF Spaces uses port 7860
    
    # Security - Using Supabase JWT
    SECRET_KEY: str = os.getenv("SUPABASE_JWT_SECRET", "your-secret-key-change-in-production")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    
    # Supabase (replaces PostgreSQL + Redis)
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "https://dtqkrrpschkofzaqrdyw.supabase.co")
    SUPABASE_ANON_KEY: str = os.getenv("SUPABASE_ANON_KEY", "")
    SUPABASE_SERVICE_KEY: str = os.getenv("SUPABASE_SERVICE_KEY", "")
    SUPABASE_JWT_SECRET: str = os.getenv("SUPABASE_JWT_SECRET", "")
    
    # Redis (optional - can use Supabase realtime or Upstash)
    REDIS_URL: str = os.getenv("REDIS_URL", "")  # Optional for advanced features
    
    # CORS - Add Hugging Face Space URL
    CORS_ORIGINS: List[str] = [
        "http://localhost",
        "http://localhost:3000",
        "http://localhost:8080",
        "https://Abbah77-Here-backend.hf.space",
        "https://huggingface.co",
        "https://*.hf.space",  # All HF Spaces
    ]
    
    @validator("CORS_ORIGINS", pre=True)
    def assemble_cors_origins(cls, v: str | List[str]) -> List[str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",")]
        return v
    
    # File Upload - Hugging Face uses /tmp
    MAX_UPLOAD_SIZE: int = 10 * 1024 * 1024  # 10MB
    TEMP_DIR: str = "/tmp/uploads"  # HF Spaces only writable location
    ALLOWED_IMAGE_TYPES: List[str] = ["image/jpeg", "image/png", "image/webp"]
    ALLOWED_VIDEO_TYPES: List[str] = ["video/mp4"]
    
    # Storage - Supabase Storage replaces AWS S3
    USE_SUPABASE_STORAGE: bool = True  # Set to False if you still want AWS S3
    SUPABASE_STORAGE_BUCKET: str = "media"  # Create this bucket in Supabase
    
    # AWS S3 (optional fallback)
    AWS_ACCESS_KEY_ID: Optional[str] = os.getenv("AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY: Optional[str] = os.getenv("AWS_SECRET_ACCESS_KEY")
    AWS_BUCKET_NAME: Optional[str] = os.getenv("AWS_BUCKET_NAME")
    AWS_REGION: Optional[str] = os.getenv("AWS_REGION", "us-east-1")
    CDN_URL: Optional[str] = os.getenv("CDN_URL")
    
    # WebSocket - Supabase Realtime
    WS_MAX_CONNECTIONS: int = 10000
    WS_PING_INTERVAL: int = 20
    WS_PING_TIMEOUT: int = 20
    USE_SUPABASE_REALTIME: bool = True  # Use Supabase realtime instead of Redis
    
    # Rate Limiting - Can use Supabase or simple in-memory
    RATE_LIMIT_REQUESTS: int = 100
    RATE_LIMIT_PERIOD: int = 60
    
    # AI/ML - Hugging Face friendly paths
    ENABLE_AI_FEATURES: bool = True
    ML_MODEL_PATH: str = "/tmp/models"  # Store models in /tmp
    HF_CACHE_DIR: str = "/tmp/huggingface"  # For Hugging Face transformers cache
    
    # Hugging Face Space specific
    HF_SPACE_ID: str = "Abbah77/Here_backend"
    HF_TOKEN: Optional[str] = os.getenv("HF_TOKEN")  # Your HF token
    
    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()