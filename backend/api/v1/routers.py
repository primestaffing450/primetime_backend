from fastapi import APIRouter
from backend.api.v1.timesheet import router as timesheet_router
from backend.api.v1.auth import router as auth_router
from backend.api.v1.manager import router as manager_router
from backend.core.v1.config import settings

# Main API router
api_router_v1 = APIRouter()

# Include routers for different endpoints
api_router_v1.include_router(auth_router, prefix="/auth", tags=["Authentication"])
api_router_v1.include_router(timesheet_router, prefix="/timesheet", tags=["Timesheet"]) 
api_router_v1.include_router(manager_router, prefix="/manager", tags=["Manager"])