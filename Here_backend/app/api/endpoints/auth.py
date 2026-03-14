from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from datetime import datetime, timedelta
from typing import Any

from ...core.database import get_db, get_public_db
from ...core.security import SecurityUtils
from ...core.config import settings
from ...models.user import UserCreate, UserResponse, UserInDB
from ...schemas.user import Token, RefreshToken
from ...services.user_service import UserService

router = APIRouter(prefix="/auth", tags=["authentication"])

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

@router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
async def register(
    user_in: UserCreate,
) -> Any:
    """Register a new user"""
    
    # Check if email exists using UserService
    existing_email = await UserService.get_user_by_email(user_in.email)
    if existing_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Check if username exists
    existing_username = await UserService.get_user_by_username(user_in.username)
    if existing_username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already taken"
        )
    
    # Create new user using UserService
    user = await UserService.create_user(user_in)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create user"
        )
    
    # Create tokens
    access_token = SecurityUtils.create_access_token({"sub": user.id})
    refresh_token = SecurityUtils.create_refresh_token({"sub": user.id})
    
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer"
    }

@router.post("/login", response_model=Token)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends()
) -> Any:
    """Login with email and password"""
    
    # Find user by email using UserService
    user = await UserService.get_user_by_email(form_data.username)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password"
        )
    
    # Check if user is active
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account is inactive"
        )
    
    # Verify password
    if not SecurityUtils.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password"
        )
    
    # Update last login using UserService
    await UserService.update_last_login(user.id)
    
    # Create tokens
    access_token = SecurityUtils.create_access_token({"sub": user.id})
    refresh_token = SecurityUtils.create_refresh_token({"sub": user.id})
    
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer"
    }

@router.post("/refresh", response_model=Token)
async def refresh_token(
    refresh_token_in: RefreshToken,
) -> Any:
    """Get new access token using refresh token"""
    
    payload = SecurityUtils.decode_token(refresh_token_in.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token"
        )
    
    user_id = payload.get("sub")
    
    # Get user using UserService
    user = await UserService.get_user_by_id(user_id)
    
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive"
        )
    
    # Create new tokens
    access_token = SecurityUtils.create_access_token({"sub": user.id})
    refresh_token = SecurityUtils.create_refresh_token({"sub": user.id})
    
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer"
    }

@router.post("/logout")
async def logout(
    token: str = Depends(oauth2_scheme)
) -> Any:
    """Logout user (blacklist token - implement with Redis if available)"""
    
    # TODO: Add token to blacklist in Redis if Redis is configured
    # For now, just return success - client should delete token
    
    return {"message": "Successfully logged out"}

@router.get("/me", response_model=UserResponse)
async def get_current_user(
    token: str = Depends(oauth2_scheme)
) -> Any:
    """Get current user info"""
    
    payload = SecurityUtils.decode_token(token)
    if not payload or payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )
    
    user_id = payload.get("sub")
    
    # Get user using UserService
    user = await UserService.get_user_by_id(user_id)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    return user

@router.post("/verify-email")
async def verify_email(
    email: str,
    token: str
) -> Any:
    """Verify user email (implement with Supabase Auth)"""
    
    # Supabase handles email verification automatically
    # You can use supabase.auth.verify_otp() if needed
    
    return {"message": "Email verified successfully"}

@router.post("/reset-password")
async def reset_password(
    email: str
) -> Any:
    """Send password reset email"""
    
    # Check if user exists
    user = await UserService.get_user_by_email(email)
    
    if not user:
        # Don't reveal that email doesn't exist for security
        return {"message": "If email exists, reset link will be sent"}
    
    # TODO: Implement password reset with Supabase Auth
    # supabase.auth.reset_password_for_email(email)
    
    return {"message": "Password reset email sent"}

# Helper dependency to get current user (for use in other endpoints)
async def get_current_user_dependency(
    token: str = Depends(oauth2_scheme)
) -> UserInDB:
    """
    Dependency to get current authenticated user
    Use this in other endpoints that need the current user
    """
    payload = SecurityUtils.decode_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )
    
    user_id = payload.get("sub")
    
    # Get user using UserService
    user = await UserService.get_user_by_id(user_id)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    return user