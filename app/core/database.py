"""
MongoDB database configuration using PyMongo.
"""

from typing import Optional
from pymongo import MongoClient
from pymongo.database import Database
from app.core.config import settings
from app.core.logging import logger


class MongoDB:
    """MongoDB connection manager."""
    client: Optional[MongoClient] = None
    db: Optional[Database] = None
    timesheet_entries: Optional[Database] = None  # Define the timesheet_entries collection
    timesheet_audit: Optional[Database] = None
    images: Optional[Database] = None

    @classmethod
    def connect_to_mongo(cls):
        """Initialize MongoDB connection."""
        if cls.client is None:
            try:
                # Build connection string based on available credentials
                connection_kwargs = {
                    "host": settings.MONGODB_HOST,
                    "port": settings.MONGODB_PORT,
                }
                
                # Only add authentication if username is provided
                if settings.MONGODB_USERNAME and settings.MONGODB_PASSWORD:
                    connection_kwargs.update({
                        "username": settings.MONGODB_USERNAME,
                        "password": settings.MONGODB_PASSWORD,
                        "authSource": "admin"
                    })
                
                # Connect to MongoDB
                logger.info(f"Connecting to MongoDB at {settings.MONGODB_HOST}:{settings.MONGODB_PORT}")
                cls.client = MongoClient(**connection_kwargs)
                
                # Test connection
                cls.client.admin.command('ping')
                
                # Get database
                cls.db = cls.client[settings.MONGODB_DB]
                
                # Define the timesheet_entries collection
                cls.timesheet_entries = cls.db["timesheet_entries"]

                # Create indexes
                cls.db.users.create_index("username", unique=True)
                cls.db.users.create_index("email", unique=True)
                
                logger.info(f"Connected to MongoDB database: {settings.MONGODB_DB}")
            except Exception as e:
                logger.error(f"Failed to connect to MongoDB: {str(e)}")
                raise

    @classmethod
    def close_mongo_connection(cls):
        """Close MongoDB connection."""
        if cls.client is not None:
            cls.client.close()
            cls.client = None
            cls.db = None
            cls.timesheet_entries = None  # Reset this line

            logger.info("Closed MongoDB connection")


# MongoDB connection instance
db = MongoDB()
