"""
Token models for authentication.
"""

from typing import Optional
from pydantic import BaseModel


class Token(BaseModel):
    """Token model for authentication responses."""
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    """Token data model."""
    user_id: Optional[str] = None 