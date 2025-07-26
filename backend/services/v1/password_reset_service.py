"""
Password reset service for handling password reset functionality.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional
import secrets

from bson import ObjectId

from backend.core.v1.config import settings
from backend.core.v1.logging import logger
from backend.core.v1.database import db
from backend.services.v1.auth_service import get_password_hash
from backend.services.v1.notification_services import EmailServices

class PasswordResetService:
    """Service for handling password reset functionality."""
    
    def __init__(self):
        self.email_service = EmailServices()
        self.reset_token_expiry = timedelta(hours=1)  # Token expires in 1 hour
    
    async def generate_reset_token(self, user_id: str) -> str:
        """Generate a password reset token for a user."""
        try:
            # Generate a secure random token
            token = secrets.token_urlsafe(32)
            
            # Store token in database with expiry
            expiry = datetime.now(timezone.utc) + self.reset_token_expiry
            db.db.password_reset_tokens.insert_one({
                "user_id": user_id,
                "token": token,
                "expires_at": expiry,
                "used": False
            })
            
            return token
        except Exception as e:
            logger.error(f"Error generating reset token: {str(e)}")
            raise
    
    async def send_reset_email(self, email: str, token: str) -> bool:
        """Send password reset email to user."""
        try:
            reset_link = f"{settings.FRONTEND_URL}/reset-password?token={token}"
            
            html_content = f"""
            <html>
            <head>
                <style>
                    body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                    .container {{ padding: 20px; }}
                    .header {{ background-color: #f8f9fa; padding: 20px; margin-bottom: 20px; }}
                    .button {{ 
                        display: inline-block;
                        padding: 10px 20px;
                        background-color: #007bff;
                        color: white;
                        text-decoration: none;
                        border-radius: 5px;
                        margin-top: 20px;
                    }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h2>Password Reset Request</h2>
                        <p>You have requested to reset your password. Click the button below to proceed.</p>
                    </div>
                    <a href="{reset_link}" class="button">Reset Password</a>
                    <p>If you did not request this password reset, please ignore this email.</p>
                    <p>This link will expire in 1 hour.</p>
                </div>
            </body>
            </html>
            """
            
            smtp_server = self.email_service.create_smtp_connection()
            try:
                message = self.email_service.create_email_message(
                    to_email=[email],
                    subject="Password Reset Request",
                    body=html_content
                )
                smtp_server.sendmail(settings.SMTP_FROM, [email], message.as_string())
                logger.info(f"Password reset email sent to {email}")
                return True
            finally:
                smtp_server.quit()
                
        except Exception as e:
            logger.error(f"Error sending reset email: {str(e)}")
            return False
    
    async def validate_reset_token(self, token: str) -> Optional[str]:
        """Validate a password reset token and return user ID if valid."""
        try:
            # Find token in database
            token_doc = db.db.password_reset_tokens.find_one({
                "token": token,
                "used": False,
                "expires_at": {"$gt": datetime.now(timezone.utc)}
            })
            
            if not token_doc:
                return None
                
            return token_doc["user_id"]
        except Exception as e:
            logger.error(f"Error validating reset token: {str(e)}")
            return None
    
    async def reset_password(self, token: str, new_password: str) -> bool:
        """Reset user's password using a valid token."""
        try:
            # Validate token
            user_id = await self.validate_reset_token(token)
            if not user_id:
                return False
            
            # Update password
            hashed_password = get_password_hash(new_password)
            db.db.users.update_one(
                {"_id": ObjectId(user_id)},
                {"$set": {
                    "hashed_password": hashed_password,
                    "updated_at": datetime.now(timezone.utc)
                }}
            )
            
            # Mark token as used
            db.db.password_reset_tokens.update_one(
                {"token": token},
                {"$set": {"used": True}}
            )
            
            logger.info(f"Password reset successfully for user: {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error resetting password: {str(e)}")
            return False 