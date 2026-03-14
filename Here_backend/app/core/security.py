from datetime import datetime, timedelta
from typing import Optional, Union, Dict, Any
from jose import JWTError, jwt
from passlib.context import CryptContext
from ..core.config import settings
import secrets
import hashlib
import hmac

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class SecurityUtils:
    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """Verify a plain password against a hashed password"""
        return pwd_context.verify(plain_password, hashed_password)
    
    @staticmethod
    def get_password_hash(password: str) -> str:
        """Hash a password"""
        return pwd_context.hash(password)
    
    @staticmethod
    def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
        """Create JWT access token"""
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        
        to_encode.update({"exp": expire, "type": "access"})
        encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
        return encoded_jwt
    
    @staticmethod
    def create_refresh_token(data: Dict[str, Any]) -> str:
        """Create JWT refresh token"""
        to_encode = data.copy()
        expire = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        to_encode.update({"exp": expire, "type": "refresh"})
        encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
        return encoded_jwt
    
    @staticmethod
    def decode_token(token: str) -> Optional[Dict[str, Any]]:
        """Decode and verify JWT token"""
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            return payload
        except JWTError:
            return None
    
    @staticmethod
    def generate_secure_token() -> str:
        """Generate a secure random token"""
        return secrets.token_urlsafe(32)
    
    @staticmethod
    def hash_token(token: str) -> str:
        """Hash a token for storage (for email verification, etc.)"""
        return hashlib.sha256(token.encode()).hexdigest()
    
    @staticmethod
    def verify_hmac_signature(message: str, signature: str, key: str) -> bool:
        """Verify HMAC signature"""
        expected = hmac.new(
            key.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

# Rate limiting helper with fallback
class RateLimiter:
    def __init__(self, redis_client=None):
        self.redis = redis_client
    
    async def is_rate_limited(self, key: str, max_requests: int, period: int) -> bool:
        """Check if a key is rate limited - falls back to no limiting if redis unavailable"""
        if not self.redis:
            return False  # No rate limiting without Redis
        
        try:
            current = await self.redis.incr(key)
            if current == 1:
                await self.redis.expire(key, period)
            return current > max_requests
        except:
            return False  # Fail open if Redis fails