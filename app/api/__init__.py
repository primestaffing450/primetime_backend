"""
API routes and endpoints.
"""

from fastapi import APIRouter
from app.api.routes.timesheet import router as timesheet_router
from app.api.routes.auth import router as auth_router
from app.api.routes.manager import router as manager_router
from app.core.config import settings

# Main API router
api_router = APIRouter()

# Include routers for different endpoints
api_router.include_router(auth_router, prefix="/auth", tags=["Authentication"])
api_router.include_router(timesheet_router, prefix="/timesheet", tags=["Timesheet"]) 
api_router.include_router(manager_router, prefix="/manager", tags=["Manager"])