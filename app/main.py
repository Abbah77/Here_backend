from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging
import asyncio
from datetime import datetime

from .core.config import settings
from .core.websocket_manager import manager
from .api.endpoints import auth, message, feed, media, websocket, stories
from .core.database import check_supabase_connection  # Import health check

# Configure logging - THIS MUST BE AT THE TOP
logging.basicConfig(
    level=logging.INFO if not settings.DEBUG else logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

# Create FastAPI app - THIS COMES NEXT
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    debug=settings.DEBUG,
    docs_url="/api/docs" if settings.DEBUG else None,
    redoc_url="/api/redoc" if settings.DEBUG else None
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers - AFTER app is created
api_prefix = settings.API_V1_PREFIX
app.include_router(auth.router, prefix=api_prefix)
app.include_router(message.router, prefix=api_prefix)
app.include_router(feed.router, prefix=api_prefix)
app.include_router(media.router, prefix=api_prefix)
app.include_router(websocket.router)  # WebSocket router has no prefix
app.include_router(stories.router, prefix=api_prefix) # Add this line


# Health check
@app.get("/health")
async def health_check():
    # Check Supabase connection
    db_status = await check_supabase_connection()
    
    return {
        "status": "healthy",
        "version": settings.APP_VERSION,
        "database": "connected" if db_status else "disconnected",
        "timestamp": datetime.utcnow().isoformat()
    }

# SINGLE startup event
@app.on_event("startup")
async def startup_event():
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    
    # Check Supabase connection
    db_status = await check_supabase_connection()
    if db_status:
        logger.info("✅ Supabase connection successful")
    else:
        logger.warning("⚠️ Supabase connection failed - check your credentials")
    
    # Initialize WebSocket manager (now uses Supabase Realtime)
    await manager.initialize()
    logger.info("✅ WebSocket manager initialized")
    
    # Start background tasks
    if settings.ENABLE_AI_FEATURES:
        try:
            from .core.tasks import schedule_heat_score_updates
            from .core.ai_tasks import schedule_ai_training
            
            # Start heat score updates (every hour)
            asyncio.create_task(schedule_heat_score_updates())
            logger.info("✅ Heat score update task scheduled")
            
            # Start AI training (once per day)
            asyncio.create_task(schedule_ai_training())
            logger.info("✅ AI training task scheduled")
            
        except ImportError as e:
            logger.warning(f"⚠️ Could not start background tasks: {e}")
    
    logger.info("🎉 Application startup complete")

# SINGLE shutdown event
@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Shutting down application...")
    
    # Clean up WebSocket connections
    await manager.cleanup()
    logger.info("✅ WebSocket manager cleaned up")
    
    logger.info("👋 Application shutdown complete")
