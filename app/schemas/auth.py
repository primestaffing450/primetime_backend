"""
Authentication schemas for request/response validation.
"""

from typing import Optional
from enum import Enum
from pydantic import BaseModel, EmailStr, Field
from app.core.config import settings

class UserRole(str, Enum):
    employee = "employee"
    manager = "manager"
    admin = "admin"


class UserBase(BaseModel):
    """Base user schema."""
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    full_name: Optional[str] = None
    # role: UserRole = Field(..., description="User role, allowed values: employee, manager, admin")
    role: Optional[UserRole] = UserRole.employee
    
    class Config:
        # This will output the enum's value ("employee") instead of "UserRole.employee"
        use_enum_values = True


class UserCreate(UserBase):
    """User creation schema."""
    password: str = Field(..., min_length=settings.PASSWORD_MIN_LENGTH, max_length=settings.PASSWORD_MAX_LENGTH)


class UserLogin(BaseModel):
    """User login schema."""
    username_or_email: str
    password: str


class UserResponse(UserBase):
    """User response schema."""
    id: str = Field(..., alias="_id")
    is_active: bool = True
    is_superuser: bool = False

    class Config:
        """Pydantic config."""
        orm_mode = True
        allow_population_by_field_name = True
        json_encoders = {str: str}


class Token(BaseModel):
    """Token response schema."""
    access_token: str
    token_type: str = "bearer"
    user_data: Optional[dict] = None

    class Config:
        """Pydantic config."""
        json_encoders = {str: str}
        populate_by_name = True


class TokenData(BaseModel):
    """Token data schema."""
    sub: str  # user_id
    username: str
    email: str
    full_name: Optional[str] = None
    role: str
    is_active: bool = True
    is_superuser: bool = False
    exp: Optional[int] = None  # expiration timestamp
    is_active: Optional[bool] = None
    is_superuser: Optional[bool] = None


class PasswordChange(BaseModel):
    """Password change schema."""
    current_password: str = Field(..., min_length=settings.PASSWORD_MIN_LENGTH, max_length=settings.PASSWORD_MAX_LENGTH)
    new_password: str = Field(..., min_length=settings.PASSWORD_MIN_LENGTH, max_length=settings.PASSWORD_MAX_LENGTH)


class PasswordResetRequest(BaseModel):
    """Password reset request schema."""
    email: EmailStr


class PasswordResetToken(BaseModel):
    """Password reset token schema."""
    token: str
    password: str = Field(..., min_length=settings.PASSWORD_MIN_LENGTH, max_length=settings.PASSWORD_MAX_LENGTH)
    confirm_password: str = Field(..., min_length=settings.PASSWORD_MIN_LENGTH, max_length=settings.PASSWORD_MAX_LENGTH)