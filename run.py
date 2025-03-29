"""
Entry point for running the FastAPI application.
"""

import uvicorn
from app.core.config import settings
from app.core.logging import logger

# Log the available endpoints for easy reference
logger.info("""
Available endpoints:
-------------------------------------------------
GET    /api/auth/test         - Test authentication routes
POST   /api/auth/login        - Login and get access token  
POST   /api/auth/register     - Register a new user
GET    /api/auth/me           - Get current user info
POST   /api/auth/change-password - Change user password
POST   /api/timesheet/upload   - Upload and process a timesheet image
-------------------------------------------------
""")

if __name__ == "__main__":
    """Run the application with uvicorn server."""
    print(f"Starting server at http://{settings.HOST}:{settings.PORT}")
    print(f"Documentation available at http://{settings.HOST}:{settings.PORT}/docs")
    
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower()
    )