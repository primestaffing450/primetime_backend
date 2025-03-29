"""
Configuration settings for the application.
"""

import os
from typing import List
from pydantic import BaseModel
# from pydantic.v1 import BaseSettings
from pydantic_settings import BaseSettings
from dotenv import load_dotenv
from fastapi_jwt_auth import AuthJWT

# Load environment variables from .env file
load_dotenv()


class JWTSettings(BaseModel):
    """JWT settings for AuthJWT."""
    authjwt_secret_key: str = os.getenv("JWT_SECRET_KEY", "your-super-secure-key-change-me")
    authjwt_token_location: set = {"headers"}
    authjwt_access_token_expires: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
    authjwt_header_name: str = "Authorization"
    authjwt_header_type: str = "Bearer"


@AuthJWT.load_config
def get_jwt_settings():
    """Load JWT settings."""
    return JWTSettings()


class Settings(BaseSettings):
    """Application settings."""
    # API keys
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    MODEL_NAME: str = os.getenv("MODEL_NAME", "gpt-4o")
    
    # Application settings
    APP_NAME: str = "Timesheet Extraction API"
    DEBUG: bool = os.getenv("DEBUG", "False").lower() in ("true", "1", "t")
    API_V1_STR: str = "/v1"
    
    # Server settings
    HOST: str = os.getenv("HOST", "localhost")
    PORT: int = int(os.getenv("PORT", "7778"))
    
    # Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    
    # CORS
    CORS_ORIGINS: List[str] = ["*"]
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ALLOW_METHODS: List[str] = ["*"]
    CORS_ALLOW_HEADERS: List[str] = ["*"]

    # MongoDB Settings - use empty string for no auth
    MONGODB_HOST: str = os.getenv("MONGODB_HOST", "localhost")
    MONGODB_PORT: int = int(os.getenv("MONGODB_PORT", "27017"))
    MONGODB_DB: str = os.getenv("MONGODB_DB", "timesheet_db")
    MONGODB_USERNAME: str = os.getenv("MONGODB_USERNAME", "")
    MONGODB_PASSWORD: str = os.getenv("MONGODB_PASSWORD", "")
    
    # Password Settings
    PASSWORD_MIN_LENGTH: int = 8
    PASSWORD_MAX_LENGTH: int = 50
    
    # SMTP Settings
    SMTP_HOST: str = os.getenv("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER: str = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
    SMTP_FROM: str = os.getenv("SMTP_FROM", "noreply@example.com")
    SMTP_FROM_NAME: str = os.getenv("SMTP_FROM_NAME", "Timesheet Extraction Service")


    IMAGE_DIR: str = os.getenv("IMAGE_DIR", "images")

    class Config:
        """Pydantic config."""
        env_file = ".env"
        extra = "ignore"


# Create a settings object that will be imported by other modules
settings = Settings() 