"""
Authentication service for handling user authentication and management.
"""

from datetime import datetime, timezone
from typing import Optional
from bson import ObjectId
from passlib.context import CryptContext
from pymongo.errors import DuplicateKeyError

from app.core.config import settings
from app.core.logging import logger
from app.core.database import db
from app.models.user import UserInDB, UserCreate

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a password against its hash.
    
    Args:
        plain_password: Plain text password
        hashed_password: Hashed password
        
    Returns:
        bool: True if password matches hash
    """
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """
    Hash a password.
    
    Args:
        password: Plain text password
        
    Returns:
        str: Hashed password
    """
    return pwd_context.hash(password)


def authenticate_user(username_or_email: str, password: str) -> Optional[UserInDB]:
    """
    Authenticate a user by username or email and password.
    
    Args:
        username_or_email: Username or email
        password: Plain text password
        
    Returns:
        Optional[UserInDB]: User if authenticated, None otherwise
    """
    try:
        # Try to find user by username
        user_dict = db.db.users.find_one({"username": username_or_email})
        
        # If not found, try by email
        if not user_dict:
            user_dict = db.db.users.find_one({"email": username_or_email})
            
        if not user_dict:
            return None
        
        user = UserInDB(**user_dict)
        if not verify_password(password, user.hashed_password):
            return None
            
        return user
    except Exception as e:
        logger.error(f"Error authenticating user: {str(e)}")
        return None


def get_user_by_username(username: str) -> Optional[UserInDB]:
    """
    Get a user by username.
    
    Args:
        username: Username
        
    Returns:
        Optional[UserInDB]: User if found, None otherwise
    """
    user_dict = db.db.users.find_one({"username": username})
    return UserInDB(**user_dict) if user_dict else None


def get_user_by_email(email: str) -> Optional[UserInDB]:
    """
    Get a user by email.
    
    Args:
        email: Email address
        
    Returns:
        Optional[UserInDB]: User if found, None otherwise
    """
    user_dict = db.db.users.find_one({"email": email})
    return UserInDB(**user_dict) if user_dict else None


def get_user_by_id(user_id: ObjectId) -> Optional[UserInDB]:
    """
    Get a user by ID.
    
    Args:
        user_id: User ID
        
    Returns:
        Optional[UserInDB]: User if found, None otherwise
    """
    try:
        user_dict = db.db.users.find_one({"_id": user_id})
        if not user_dict:
            return None
        
        # Ensure _id is converted to string for serialization
        user_dict["_id"] = str(user_dict["_id"])
        
        # Return the user model
        return UserInDB(**user_dict)
    except Exception as e:
        logger.error(f"Error getting user by ID: {str(e)}")
        return None


def create_user(user_data: UserCreate) -> UserInDB:
    """
    Create a new user.
    
    Args:
        user_data: User data
        
    Returns:
        UserInDB: Created user
        
    Raises:
        ValueError: If username or email already exists
    """
    try:
        # Check if username exists
        if get_user_by_username(user_data.username):
            raise ValueError("Username already registered")
        
        # Check if email exists
        if get_user_by_email(user_data.email):
            raise ValueError("Email already registered")
        
        # Get current time once to ensure created_at and updated_at are the same
        current_time = datetime.now(timezone.utc)
        
        # Create user document
        user_dict = user_data.dict(exclude={"password"})
        user_dict.update({
            "hashed_password": get_password_hash(user_data.password),
            "created_at": current_time,
            "updated_at": current_time
        })
        
        # Insert into database
        result = db.db.users.insert_one(user_dict)
        
        # Get the created user
        created_user = get_user_by_id(result.inserted_id)
        if not created_user:
            raise ValueError("Failed to create user")
            
        return created_user
    
    except DuplicateKeyError:
        raise ValueError("Username or email already exists")
    except Exception as e:
        logger.error(f"Error creating user: {str(e)}")
        raise 