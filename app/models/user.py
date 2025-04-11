"""
User model for MongoDB storage using Pydantic.
"""

from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field, EmailStr
from bson import ObjectId


# class PyObjectId(ObjectId):
#     """Custom type for handling MongoDB ObjectId."""
#     @classmethod
#     def __get_validators__(cls):
#         yield cls.validate

#     @classmethod
#     def validate(cls, v):
#         if not ObjectId.is_valid(v):
#             raise ValueError("Invalid ObjectId")
#         return ObjectId(v)

#     @classmethod
#     def __get_pydantic_json_schema__(cls, field_schema):
#         field_schema.update(type="string")
#         return field_schema


from bson import ObjectId

class PyObjectId(ObjectId):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, value, values, config, field):
        if not ObjectId.is_valid(value):
            raise ValueError("Invalid object id")
        return ObjectId(value)

    @classmethod
    def __get_pydantic_json_schema__(cls, field_schema):
        field_schema.update(type="string")
        return field_schema


class UserBase(BaseModel):
    """Base User model."""
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    full_name: Optional[str] = None
    is_active: bool = True
    is_superuser: bool = False
    

class UserCreate(UserBase):
    """User creation model."""
    password: str

class UserInDB(UserBase):
    """User model as stored in database."""
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    hashed_password: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    role: str

    class Config:
        """Pydantic config."""
        json_encoders = {ObjectId: str}
        populate_by_name = True

class UserResponse(UserBase):
    """User response model."""
    id: str = Field(..., alias="_id")
    username: str
    email: str
    full_name: str
    role: str
    is_active: bool = True
    is_superuser: bool = False
    created_at: datetime
    updated_at: Optional[datetime] = None
    timesheet_count: Optional[int] = 0
    timesheets: Optional[List[Dict[str, Any]]] = []
    timesheet_summary: Optional[Dict[str, Any]] = None

    class Config:
        allow_population_by_field_name = True
        from_attributes = True
        populate_by_name = True 
        
        
class RoleUpdate(BaseModel):
    role: str