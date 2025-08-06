import os
import sys
from getpass import getpass

# Add the project root to the Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(project_root)

from backend.core.v1.database import db
from backend.services.v1.auth_service import create_user
from backend.schemas.v1.auth import UserCreate, UserRole
from backend.core.v1.logging import logger

def create_manager_user():
    """
    Creates a new manager user in the database.
    """
    try:
        # Connect to the database
        db.connect_to_mongo()
        logger.info("Successfully connected to the database.")

        # Get manager details from user input
        username = input("Enter username: ")
        email = input("Enter email: ")
        password = getpass("Enter password: ")
        full_name = input("Enter full name: ")

        # Create user data object
        user_data = UserCreate(
            username=username,
            email=email,
            password=password,
            full_name=full_name,
            role=UserRole.manager
        )

        # Create the user
        manager = create_user(user_data)
        logger.info(f"Manager '{manager.username}' created successfully.")

    except Exception as e:
        logger.error(f"Failed to create manager: {e}")
    finally:
        # Close the database connection
        db.close_mongo_connection()
        logger.info("Database connection closed.")

if __name__ == "__main__":
    create_manager_user() 