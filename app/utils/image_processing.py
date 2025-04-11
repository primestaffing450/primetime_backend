"""
Utility functions for image processing and text extraction.
"""

import base64
# import pytesseract
from PIL import Image
import io
from app.core.logging import logger

# Set Tesseract executable path
# pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

def extract_text_from_image(file_bytes: bytes) -> str:
    """
    Extract text from an image using Tesseract OCR.
    
    Args:
        file_bytes: Raw bytes of the image file
        
    Returns:
        str: Extracted text from the image
    """
    try:
        # Create an in-memory image from bytes
        image = Image.open(io.BytesIO(file_bytes))
        
        # Extract text using Tesseract
        extracted_text = pytesseract.image_to_string(image)
        
        # Log the extracted text for debugging
        logger.debug(f"Extracted text: {extracted_text[:100]}...")
        
        return extracted_text
    except Exception as e:
        logger.error(f"Error in extract_text_from_image: {str(e)}")
        return ""


def encode_image_to_base64(file_bytes: bytes) -> str:
    """
    Encode image bytes to base64 string.
    
    Args:
        file_bytes: Raw bytes of the image file
        
    Returns:
        str: Base64 encoded string of the image
    """
    return base64.b64encode(file_bytes).decode("utf-8")


def encode_image_from_path(image_path: str) -> str:
    """
    Read image file from disk and encode to base64.
    
    Args:
        image_path: Path to the image file
        
    Returns:
        str: Base64 encoded string of the image
    """
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8") 