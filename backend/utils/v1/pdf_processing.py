import fitz  # PyMuPDF
from PIL import Image
import io
from app.core.logging import logger

def convert_pdf_to_image(pdf_bytes: bytes) -> bytes:
    """Convert first page of PDF to image bytes."""
    try:
        # Open PDF from bytes
        pdf_document = fitz.open(stream=pdf_bytes, filetype="pdf")        
        if pdf_document.page_count == 0:
            raise ValueError("PDF document is empty")
            
        # Get first page
        page = pdf_document[0]
        
        # Convert to image with higher resolution
        zoom = 2  # Increase zoom for better quality
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        
        # Convert to PIL Image
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        
        # Save as high-quality JPEG
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='JPEG', quality=95)
        img_byte_arr.seek(0)
        
        pdf_document.close()
        return img_byte_arr.getvalue()
        
    except Exception as e:
        logger.error(f"Error converting PDF to image: {str(e)}")
        raise ValueError(f"Failed to process PDF: {str(e)}")