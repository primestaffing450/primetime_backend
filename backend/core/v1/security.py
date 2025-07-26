"""
Security utilities.
"""

from datetime import datetime, timedelta, timezone
from typing import Any

from bson import ObjectId
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi_jwt_auth import AuthJWT
from fastapi_jwt_auth.exceptions import AuthJWTException
from passlib.context import CryptContext

from backend.core.v1.config import settings
from backend.core.v1.logging import logger
from backend.schemas.v1.auth import UserRole
from backend.services.v1.auth_service import get_user_by_id

# Constants
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against a hashed password."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a password."""
    return pwd_context.hash(password)


def create_access_token(data: dict[str, Any], Authorize: AuthJWT, expires_delta: timedelta | None = None) -> str:
    """Create a JWT access token."""
    try:
        if expires_delta:
            return Authorize.create_access_token(
                subject=data["sub"],
                expires_time=expires_delta
            )
        return Authorize.create_access_token(
            subject=data["sub"],
            expires_time=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        )
    except Exception as e:
        logger.error(f"Error creating access token: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not create access token: {str(e)}"
        )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    Authorize: AuthJWT = Depends()
):
    """Get the current user from the token."""
    try:
        # Get token from credentials
        token = credentials.credentials
        
        # Set raw token for AuthJWT
        Authorize.get_raw_jwt(token)
        
        # Verify token
        Authorize.jwt_required()
        
        # Get user ID from token
        user_id = Authorize.get_jwt_subject()
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token subject",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Get user from database
        logger.info(f"Getting user with ID: {user_id}")
        user = get_user_by_id(ObjectId(user_id))
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Convert user for response
        user_dict = {
            "_id": str(user.id),  # Ensure this is a string
            "username": user.username,
            "email": user.email,
            "full_name": user.full_name,
            "is_active": user.is_active,
            "is_superuser": user.is_superuser,
            "role": user.role
        }
        
        from app.schemas.auth import UserResponse
        return UserResponse.parse_obj(user_dict)
        
    except AuthJWTException as e:
        logger.warning(f"JWT authentication failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as e:
        logger.error(f"Authentication error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication failed: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        ) 
        
        
# Manager Role Verification
def verify_manager_role(current_user=Depends(get_current_user)):
    if current_user.role not in [UserRole.admin, UserRole.manager]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access forbidden: Managers only"
        )
    return current_user