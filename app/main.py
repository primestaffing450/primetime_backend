"""
Main FastAPI application.
"""

from fastapi import FastAPI
import os
from pathlib import Path
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
import uvicorn

from app.api import api_router
from app.core.config import settings
from app.core.logging import logger
from app.core.database import db

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
app.include_router(api_router, prefix="/api")

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