"""
Main FastAPI application.
"""

from contextlib import asynccontextmanager
import os
from pathlib import Path
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import uvicorn


BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(BASE_DIR))


from backend.api.v1.routers import api_router_v1
from backend.core.v1.config import settings
from backend.core.v1.logging import logger
from backend.core.v1.database import db

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle startup and shutdown events."""
    # Startup
    logger.info("Initializing database connection...")
    db.connect_to_mongo()
    
    yield
    
    # Shutdown
    logger.info("Closing database connection...")
    db.close_mongo_connection()

# Create FastAPI app
app = FastAPI(
    title=settings.APP_NAME,
    debug=settings.DEBUG,
    lifespan=lifespan,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=settings.CORS_ALLOW_METHODS,
    allow_headers=settings.CORS_ALLOW_HEADERS,
)


UPLOAD_DIR = settings.IMAGE_DIR
Path(UPLOAD_DIR).mkdir(parents=True, exist_ok=True)

# Mount the static files directory. Files in the "uploads" folder will be available at /uploads.
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# Include API router
app.include_router(api_router_v1, prefix="/api")

@app.get("/")
async def root():
    """Root endpoint."""
    return {"message": "Welcome to Timesheet Extraction API"}


if __name__ == "__main__":
    # Run application with uvicorn
    logger.info(f"Starting application on {settings.HOST}:{settings.PORT}")
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG
    )