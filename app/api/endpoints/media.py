import os
import uuid
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, BackgroundTasks, Query
from fastapi.responses import JSONResponse
from typing import Optional, List, Dict, Any
from datetime import datetime
import hashlib
import magic
from PIL import Image
import io
import asyncio

from ...core.database import supabase
from ...core.config import settings
from ...core.security import SecurityUtils
from ...models.user import UserInDB
from ...services.user_service import UserService
from ..endpoints.auth import get_current_user_dependency

router = APIRouter(prefix="/media", tags=["media"])

# ============= SUPABASE STORAGE CONFIGURATION =============

class SupabaseStorageManager:
    """Handle all Supabase Storage operations"""
    
    def __init__(self):
        self.bucket_name = settings.SUPABASE_STORAGE_BUCKET
        self.supabase = supabase
        
    async def upload_file(
        self,
        file_data: bytes,
        file_path: str,
        content_type: str,
        metadata: Optional[Dict] = None
    ) -> str:
        """Upload file to Supabase Storage"""
        try:
            # Upload to Supabase Storage
            result = self.supabase.storage \
                .from_(self.bucket_name) \
                .upload(file_path, file_data, {
                    "content-type": content_type,
                    "x-upsert": "true"  # Overwrite if exists
                })
            
            # Get public URL
            public_url = self.supabase.storage \
                .from_(self.bucket_name) \
                .get_public_url(file_path)
            
            # Store metadata in database if needed
            if metadata:
                # You could store metadata in a 'media' table
                pass
            
            return public_url
                
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to upload to Supabase Storage: {str(e)}"
            )
    
    async def delete_file(self, file_path: str) -> bool:
        """Delete file from Supabase Storage"""
        try:
            self.supabase.storage \
                .from_(self.bucket_name) \
                .remove([file_path])
            return True
        except Exception as e:
            print(f"Error deleting file: {e}")
            return False
    
    def extract_path_from_url(self, url: str) -> Optional[str]:
        """Extract storage path from URL"""
        # Supabase URL format: https://[project].supabase.co/storage/v1/object/public/[bucket]/[path]
        try:
            if "storage/v1/object/public/" in url:
                parts = url.split(f"storage/v1/object/public/{self.bucket_name}/")
                if len(parts) > 1:
                    return parts[1]
            return None
        except:
            return None

storage_manager = SupabaseStorageManager()

# ============= MEDIA PROCESSING =============

class MediaProcessor:
    """Handle image/video processing and optimization"""
    
    ALLOWED_IMAGES = {'image/jpeg', 'image/png', 'image/webp', 'image/gif'}
    ALLOWED_VIDEOS = {'video/mp4', 'video/quicktime', 'video/x-msvideo'}
    ALLOWED_AUDIO = {'audio/mpeg', 'audio/wav', 'audio/ogg'}
    
    MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10MB
    MAX_VIDEO_SIZE = 100 * 1024 * 1024  # 100MB
    MAX_AUDIO_SIZE = 50 * 1024 * 1024   # 50MB
    
    @staticmethod
    def validate_file(file: UploadFile) -> Dict[str, Any]:
        """Validate file type and size"""
        
        # Read first few bytes to detect MIME type
        content = file.file.read(2048)
        file.file.seek(0)  # Reset pointer
        
        mime = magic.from_buffer(content, mime=True)
        size = file.size
        
        # Determine file type
        if mime in MediaProcessor.ALLOWED_IMAGES:
            file_type = "image"
            max_size = MediaProcessor.MAX_IMAGE_SIZE
        elif mime in MediaProcessor.ALLOWED_VIDEOS:
            file_type = "video"
            max_size = MediaProcessor.MAX_VIDEO_SIZE
        elif mime in MediaProcessor.ALLOWED_AUDIO:
            file_type = "audio"
            max_size = MediaProcessor.MAX_AUDIO_SIZE
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported file type: {mime}"
            )
        
        # Check size
        if size > max_size:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File too large. Max size: {max_size // (1024*1024)}MB"
            )
        
        return {
            "mime_type": mime,
            "file_type": file_type,
            "size": size,
            "extension": mime.split('/')[-1]
        }
    
    @staticmethod
    async def generate_thumbnail(
        image_data: bytes,
        max_size: tuple = (200, 200)
    ) -> bytes:
        """Generate thumbnail from image"""
        try:
            img = Image.open(io.BytesIO(image_data))
            img.thumbnail(max_size, Image.Resampling.LANCZOS)
            
            # Save to bytes
            thumb_io = io.BytesIO()
            img.save(thumb_io, format='JPEG', quality=85)
            return thumb_io.getvalue()
            
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to generate thumbnail: {str(e)}"
            )
    
    @staticmethod
    def generate_file_path(
        user_id: str,
        file_type: str,
        extension: str,
        is_thumbnail: bool = False
    ) -> str:
        """Generate unique storage path for file"""
        timestamp = datetime.utcnow().strftime("%Y/%m/%d")
        unique_id = str(uuid.uuid4())
        
        if is_thumbnail:
            return f"users/{user_id}/{file_type}/thumbnails/{timestamp}/{unique_id}.jpg"
        else:
            return f"users/{user_id}/{file_type}/{timestamp}/{unique_id}.{extension}"

# ============= UPLOAD ENDPOINTS =============

@router.post("/upload")
async def upload_media(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    media_type: str = Form(...),  # 'post', 'message', 'profile'
    current_user: UserInDB = Depends(get_current_user_dependency)
):
    """Upload media file to Supabase Storage"""
    
    # Validate file
    file_info = MediaProcessor.validate_file(file)
    
    # Read file data
    file_data = await file.read()
    
    # Generate file hash for deduplication
    file_hash = hashlib.sha256(file_data).hexdigest()
    
    # Generate storage path
    file_path = MediaProcessor.generate_file_path(
        user_id=current_user.id,
        file_type=file_info['file_type'],
        extension=file_info['extension']
    )
    
    # Upload to Supabase Storage
    url = await storage_manager.upload_file(
        file_data=file_data,
        file_path=file_path,
        content_type=file_info['mime_type'],
        metadata={
            'user_id': current_user.id,
            'media_type': media_type,
            'file_hash': file_hash,
            'original_name': file.filename
        }
    )
    
    # Generate thumbnail for images
    thumbnail_url = None
    if file_info['file_type'] == 'image':
        background_tasks.add_task(
            generate_and_upload_thumbnail,
            file_data=file_data,
            user_id=current_user.id,
            original_path=file_path
        )
        # For immediate response, generate sync thumbnail
        thumbnail_data = await MediaProcessor.generate_thumbnail(file_data)
        thumbnail_path = MediaProcessor.generate_file_path(
            user_id=current_user.id,
            file_type='image',
            extension='jpg',
            is_thumbnail=True
        )
        thumbnail_url = await storage_manager.upload_file(
            file_data=thumbnail_data,
            file_path=thumbnail_path,
            content_type='image/jpeg',
            metadata={'original': file_path}
        )
    
    return {
        "url": url,
        "thumbnail_url": thumbnail_url,
        "file_type": file_info['file_type'],
        "mime_type": file_info['mime_type'],
        "size": file_info['size'],
        "path": file_path
    }

@router.post("/upload/multiple")
async def upload_multiple_media(
    files: List[UploadFile] = File(...),
    media_type: str = Form(...),
    current_user: UserInDB = Depends(get_current_user_dependency)
):
    """Upload multiple media files"""
    
    results = []
    
    for file in files:
        try:
            # Validate file
            file_info = MediaProcessor.validate_file(file)
            
            # Read file data
            file_data = await file.read()
            
            # Generate storage path
            file_path = MediaProcessor.generate_file_path(
                user_id=current_user.id,
                file_type=file_info['file_type'],
                extension=file_info['extension']
            )
            
            # Upload to Supabase Storage
            url = await storage_manager.upload_file(
                file_data=file_data,
                file_path=file_path,
                content_type=file_info['mime_type']
            )
            
            results.append({
                "url": url,
                "file_type": file_info['file_type'],
                "mime_type": file_info['mime_type'],
                "size": file_info['size'],
                "filename": file.filename,
                "path": file_path,
                "status": "success"
            })
            
        except Exception as e:
            results.append({
                "filename": file.filename,
                "status": "error",
                "error": str(e)
            })
    
    return {"results": results}

@router.post("/upload/profile-picture")
async def upload_profile_picture(
    file: UploadFile = File(...),
    current_user: UserInDB = Depends(get_current_user_dependency)
):
    """Upload profile picture"""
    
    # Validate image
    file_info = MediaProcessor.validate_file(file)
    
    if file_info['file_type'] != 'image':
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Profile picture must be an image"
        )
    
    # Read file data
    file_data = await file.read()
    
    # Generate multiple sizes
    sizes = {
        'original': file_data,
        'large': await MediaProcessor.generate_thumbnail(file_data, (500, 500)),
        'medium': await MediaProcessor.generate_thumbnail(file_data, (200, 200)),
        'small': await MediaProcessor.generate_thumbnail(file_data, (50, 50))
    }
    
    urls = {}
    
    # Upload each size
    for size_name, size_data in sizes.items():
        file_path = MediaProcessor.generate_file_path(
            user_id=current_user.id,
            file_type='profile',
            extension='jpg',
            is_thumbnail=(size_name != 'original')
        )
        
        url = await storage_manager.upload_file(
            file_data=size_data,
            file_path=file_path,
            content_type='image/jpeg',
            metadata={'size': size_name}
        )
        
        urls[size_name] = url
    
    # Update user profile
    await UserService.update_user(current_user.id, UserUpdate(
        profile_pic_url=urls['medium']
    ))
    
    # Delete old profile pictures (background task)
    if current_user.profile_pic_url:
        old_path = storage_manager.extract_path_from_url(current_user.profile_pic_url)
        if old_path:
            # Background deletion of old files
            asyncio.create_task(delete_old_profile_pictures(old_path))
    
    return {
        "urls": urls,
        "default_url": urls['medium']
    }

# ============= THUMBNAIL GENERATION =============

async def generate_and_upload_thumbnail(
    file_data: bytes,
    user_id: str,
    original_path: str
):
    """Background task to generate and upload thumbnail"""
    try:
        thumbnail_data = await MediaProcessor.generate_thumbnail(file_data)
        
        thumbnail_path = MediaProcessor.generate_file_path(
            user_id=user_id,
            file_type='image',
            extension='jpg',
            is_thumbnail=True
        )
        
        await storage_manager.upload_file(
            file_data=thumbnail_data,
            file_path=thumbnail_path,
            content_type='image/jpeg',
            metadata={'original': original_path}
        )
        
    except Exception as e:
        print(f"Failed to generate thumbnail: {e}")

async def delete_old_profile_pictures(old_path: str):
    """Delete old profile picture files"""
    try:
        # Extract directory path
        directory = "/".join(old_path.split("/")[:-1])
        
        # List all files in directory
        # Note: Supabase doesn't have direct list by prefix, 
        # you might need to store references in a database table
        await storage_manager.delete_file(old_path)
        
    except Exception as e:
        print(f"Failed to delete old profile pictures: {e}")

# ============= DOWNLOAD/STREAM ENDPOINTS =============

@router.get("/download/{path:path}")
async def download_media(
    path: str,
    current_user: Optional[UserInDB] = Depends(get_current_user_dependency)
):
    """Get public URL for media file"""
    
    # Generate public URL
    url = supabase.storage \
        .from_(storage_manager.bucket_name) \
        .get_public_url(path)
    
    if not url:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found"
        )
    
    return {"url": url}

@router.delete("/{path:path}")
async def delete_media(
    path: str,
    current_user: UserInDB = Depends(get_current_user_dependency)
):
    """Delete media file (only if owned by user)"""
    
    # Check if user owns this file
    if not path.startswith(f"users/{current_user.id}/"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this file"
        )
    
    # Delete file
    success = await storage_manager.delete_file(path)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete file"
        )
    
    return {"status": "deleted", "path": path}

# ============= MEDIA METADATA =============

@router.get("/info/{path:path}")
async def get_media_info(
    path: str,
    current_user: UserInDB = Depends(get_current_user_dependency)
):
    """Get media file metadata"""
    
    try:
        # Supabase doesn't have direct metadata API
        # You might need to store metadata in a database table
        return {
            "path": path,
            "url": supabase.storage.from_(storage_manager.bucket_name).get_public_url(path),
            "note": "Metadata not available directly from Supabase Storage"
        }
            
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found"
        )

# ============= OPTIMIZED URLS =============

@router.get("/optimized-url/{path:path}")
async def get_optimized_url(
    path: str,
    width: Optional[int] = Query(None, ge=10, le=2000),
    height: Optional[int] = Query(None, ge=10, le=2000),
    quality: int = Query(80, ge=1, le=100)
):
    """Get optimized image URL (Supabase supports image transformation)"""
    
    base_url = supabase.storage \
        .from_(storage_manager.bucket_name) \
        .get_public_url(path)
    
    # Supabase supports image transformation via query params
    if width or height:
        params = []
        if width:
            params.append(f"width={width}")
        if height:
            params.append(f"height={height}")
        params.append(f"quality={quality}")
        
        # Supabase transformation format
        # https://[project].supabase.co/storage/v1/render/image/public/[bucket]/[path]?width=200&height=200
        transform_url = base_url.replace(
            "/object/public/", 
            "/render/image/public/"
        )
        
        return {"url": f"{transform_url}?{'&'.join(params)}"}
    
    return {"url": base_url}

# ============= CREATE BUCKET (run once) =============

@router.post("/create-bucket")
async def create_bucket(
    current_user: UserInDB = Depends(get_current_user_dependency)
):
    """Create storage bucket (admin only)"""
    
    # Check if user is admin (you can implement admin check)
    # For now, just create the bucket
    
    try:
        supabase.storage.create_bucket(
            settings.SUPABASE_STORAGE_BUCKET,
            options={
                "public": True,
                "allowed_mime_types": [
                    "image/jpeg", "image/png", "image/webp", "image/gif",
                    "video/mp4", "video/quicktime",
                    "audio/mpeg", "audio/wav", "audio/ogg"
                ],
                "file_size_limit": settings.MAX_UPLOAD_SIZE
            }
        )
        return {"message": f"Bucket '{settings.SUPABASE_STORAGE_BUCKET}' created successfully"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create bucket: {str(e)}"
        )