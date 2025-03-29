"""
Logging configuration for the application.
"""

import logging
import sys
from app.core.config import settings

# Configure logger
def setup_logging():
    """Set up logging configuration."""
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    
    # Configure root logger
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            # Add file handler if needed
            # logging.FileHandler("app.log"),
        ],
    )
    
    # Disable noisy loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    
    # Create a logger for the application
    logger = logging.getLogger("app")
    logger.setLevel(log_level)
    
    return logger

# Application logger
logger = setup_logging() 