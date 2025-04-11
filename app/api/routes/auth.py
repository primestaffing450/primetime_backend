"""
Authentication routes for user management and token handling.
"""

from datetime import datetime, timedelta, timezone
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm
from fastapi_jwt_auth import AuthJWT
from fastapi_jwt_auth.exceptions import AuthJWTException
from app.schemas.auth import UserRole

from app.core.security import (
    get_password_hash,
    create_access_token,
    get_current_user,
)
from app.core.database import db
from app.core.logging import logger
from app.services.auth_service import (
    authenticate_user,
    create_user,
    get_user_by_id,
    get_user_by_email,
)
from app.schemas.auth import (
    UserCreate,
    UserResponse,
    Token,
    PasswordChange,
    UserLogin,
    PasswordResetRequest,
    PasswordResetToken,
)
from app.services.password_reset_service import PasswordResetService

router = APIRouter()


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(user_data: UserCreate) -> UserResponse:
    """
    Register new user.
    """
    logger.info(f"Register endpoint called with username: {user_data.username}")
    
    try:
        
        if user_data.role not in [UserRole.employee, UserRole.manager, UserRole.admin]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid role",
            )
        
        
        # Create user and get DB model
        user_db = create_user(user_data)
        logger.info(f"User created successfully: {user_db.username}")
        
        # Convert to response model with explicit mapping
        # Make sure to convert the ObjectId to string
        user_response = {
            "_id": str(user_db.id),  # Ensure this is a string
            "username": user_db.username,
            "email": user_db.email,
            "full_name": user_db.full_name,
            "is_active": user_db.is_active,
            "is_superuser": user_db.is_superuser,
            "role": user_db.role,
            
        }
        
        # Return using UserResponse model
        return UserResponse.parse_obj(user_response)
    except ValueError as e:
        logger.error(f"Registration error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/login", response_model=Token)
async def login(
    user_data: UserLogin,
    Authorize: AuthJWT = Depends()
) -> Token:
    try:
        logger.info(f"Login attempt for user: {user_data.username_or_email}")
        user = authenticate_user(user_data.username_or_email, user_data.password)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Incorrect username/email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Log successful login and user ID
        logger.info(f"User authenticated successfully: {user.username} (ID: {user.id})")
        
        # Prepare user data for token and response
        user_data_dict = {
            "_id": str(user.id),
            "username": user.username,
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role,
            "is_active": user.is_active,
            "is_superuser": user.is_superuser
        }

        access_token = create_access_token(
            data={"sub": str(user.id)},  # Keep only the subject in token data
            Authorize=Authorize,
            expires_delta=timedelta(minutes=60)
        )
        
        logger.info(f"Generated token for user: {user.username}")
        # Return token with user data
        return Token(
            access_token=access_token,
            token_type="bearer",
            user_data=user_data_dict
        )
    except Exception as e:
        logger.error(f"Login error: {str(e)}")
        raise


@router.post("/manager/login", response_model=Token)
async def manager_login(
    user_data: UserLogin,
    Authorize: AuthJWT=Depends()
) -> Token:
    """
        login the manger
    """

    try:
        logger.info(f"Manager login attempt for user: {user_data.username_or_email}")
        user = authenticate_user(user_data.username_or_email, user_data.password)

        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username/email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        if user.role not in [UserRole.manager, UserRole.admin]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access forbidden: Managers only"
            )
        # Log successful login and user ID
        logger.info(f"Manager authenticated successfully: {user.username} (ID: {user.id})")
        
        # Prepare user data for token and response
        user_data_dict = {
            "_id": str(user.id),
            "username": user.username,
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role,
            "is_active": user.is_active,
            "is_superuser": user.is_superuser
        }

        access_token = create_access_token(
            data={"sub": str(user.id)},
            Authorize=Authorize,
            expires_delta=timedelta(minutes=60)
        )
        
        logger.info(f"Generated token for manager: {user.username}")
        return Token(
            access_token=access_token,
            token_type="bearer",
            user_data=user_data_dict
        )

    except Exception as e:
        logger.error(f"Manager login error: {str(e)}")
        raise


@router.get("/me", response_model=UserResponse)
async def read_users_me(
    request: Request,
    current_user: UserResponse = Depends(get_current_user)
) -> UserResponse:
    """
    Get current user information.
    """
    logger.info(f"Getting profile for user: {current_user.username}")
    return current_user


@router.post("/change-password", response_model=UserResponse)
async def change_password(
    request: Request,
    password_data: PasswordChange,
    current_user: UserResponse = Depends(get_current_user)
) -> UserResponse:
    """
    Change user password.
    """
    logger.info(f"Password change requested for user: {current_user.username}")
    user = get_user_by_id(ObjectId(current_user.id))
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    if not authenticate_user(user.username, password_data.current_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect password"
        )
    
    # Update password in MongoDB
    new_password_hash = get_password_hash(password_data.new_password)
    db.db.users.update_one(
        {"_id": ObjectId(user.id)},
        {"$set": {
            "hashed_password": new_password_hash,
            "updated_at": datetime.now(timezone.utc)
        }}
    )
    
    logger.info(f"Password updated successfully for user: {current_user.username}")
    return current_user


@router.post("/forgot-password", status_code=status.HTTP_200_OK)
async def forgot_password(request: PasswordResetRequest):
    """
    Request password reset for a user.
    """
    try:
        # Get user by email
        user = get_user_by_email(request.email)
        if not user:
            # Return success even if user not found to prevent email enumeration
            return {"message": "User not found"}
        
        # Generate reset token
        reset_service = PasswordResetService()
        token = await reset_service.generate_reset_token(str(user.id))
        
        # Send reset email
        await reset_service.send_reset_email(user.email, token)
        
        return {"message": "Password reset link sent"}
    except Exception as e:
        logger.error(f"Error in forgot password: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while processing your request"
        )

@router.post("/reset-password", status_code=status.HTTP_200_OK)
async def reset_password(request: PasswordResetToken):
    """
    Reset user password using a valid token.
    """
    try:
        # Validate passwords match
        if request.password != request.confirm_password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Passwords do not match"
            )
        
        # Reset password
        reset_service = PasswordResetService()
        success = await reset_service.reset_password(request.token, request.password)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired reset token"
            )
        
        return {"message": "Password has been reset successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in reset password: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while processing your request"
        )