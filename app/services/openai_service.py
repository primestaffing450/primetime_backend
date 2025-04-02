"""
OpenAI integration service for extracting timesheet information.
"""

import json
from openai import OpenAI
from typing import Dict, Any, Optional
from app.core.logging import logger
from app.core.config import settings
from app.schemas.timesheet import TimesheetData, TimesheetRecord


# Define prompts
SYSTEM_PROMPT = """You are a helpful assistant that extracts timesheet information from images.
Your task is to analyze the provided image and extract the following information for each timesheet entry:
- date: The date in MM-DD-YYYY format
- time_in: The time in (start time) in HH:MM format (24-hour)
- time_out: The time out (end time) in HH:MM format (24-hour)
- lunch_timeout: The lunch/break duration in minutes (numeric)
- total_hours: The total hours worked as a decimal

Return your response as a JSON object with an array of 'records', where each record contains the extracted information for one timesheet entry.
Example format:
{
  "records": [
    {
      "date": "01-07-2023",
      "time_in": "09:00",
      "time_out": "17:00",
      "lunch_timeout": 30,
      "total_hours": 7.5
    },
    {
      "date": "01-07-2023",
      "time_in": "09:30",
      "time_out": "18:00",
      "lunch_timeout": 45,
      "total_hours": 7.75
    }
  ]
}

If there is only one timesheet entry, still use the 'records' array with a single object.
If you're uncertain about any value, provide your best guess based on the available information.
"""

EXTRACTION_PROMPT_TEMPLATE = """
Extract all timesheet information from the provided image.

If OCR text is available, use it as a reference: {ocr_text}

Extract each timesheet record with the following information:
- date (in MM-DD-YYYY format)
- time_in (in HH:MM 24-hour format)
- time_out (in HH:MM 24-hour format)
- lunch_timeout (in minutes)
- total_hours (as a decimal)

Please format your response as a JSON object with an array of 'records'.
"""


def generate_response(openai_client: OpenAI, base64_image: str, ocr_text: str) -> str:
    """
    Generate timesheet extraction response from OpenAI.
    
    Args:
        openai_client: OpenAI client instance
        base64_image: Base64 encoded image
        ocr_text: OCR text extracted from the image
        
    Returns:
        str: JSON response from OpenAI
        
    Raises:
        RuntimeError: If OpenAI API call fails
    """
    try:
        extraction_prompt = EXTRACTION_PROMPT_TEMPLATE.format(ocr_text=ocr_text)
        logger.info("Sending request to OpenAI API...")
        
        response = openai_client.chat.completions.create(
            model=settings.MODEL_NAME,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": extraction_prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            },
                        },
                    ],
                },
            ],
            temperature=0.7,
            top_p=0.3,
            max_tokens=1000,
            response_format={"type": "json_object"},
        )
        # print("response", response)
        content = response.choices[0].message.content
        
        if not content:
            # print("refusal", response.choices[0].message.refusal)
            return {'refusal': response.choices[0].message.refusal}
        
        logger.info(f"Received response from OpenAI: {content[:100]}...")

        # logger.info(f"Received response from OpenAI: {content}...")


        return content

    except Exception as e:
        logger.error(f"Error generating timesheet info: {str(e)}")
        raise RuntimeError(f"Failed to process timesheet image: {str(e)}")


class TimesheetImageExtractor:
    """
    Class for extracting timesheet information from images using OpenAI.
    """
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize with API key.
        
        Args:
            api_key: OpenAI API key, defaults to the one in settings if None
        """
        self.openai_client = OpenAI(api_key=api_key or settings.OPENAI_API_KEY)

    def extract_image_info(self, base64_image: str, ocr_text: str) -> Dict[str, Any]:
        """
        Extract timesheet information from an image.
        
        Args:
            base64_image: Base64 encoded image
            ocr_text: OCR text extracted from the image
            
        Returns:
            Dict containing extracted data and status
            
        Example:
            {
                "data": TimesheetData(records=[...]),
                "status": "success"
            }
        """
        try:
            response_json = generate_response(
                self.openai_client, base64_image=base64_image, ocr_text=ocr_text
            )
            
            # Parse the JSON string into a Python dictionary
            # raw_data = json.loads(response_json)
            
            # print('responseJson', response_json)
            if isinstance(response_json, str):
                raw_data = json.loads(response_json)
            else:
                raw_data = response_json
            
            print('raw',raw_data)
            # if not able to find the information from the image
            if raw_data.get('refusal'):
                print("raw_data", raw_data.get('refusal'))
                return {"data": None, "status": "error", "message": f"{raw_data.get('refusal')}"}


            # Extract records directly from raw_data
            records = raw_data.get("records", [])
            
            # If no records are found, return an error immediately.
            # if not records or len(records) == 0:
            #     logger.info("No record found in raw data")
            #     return {
            #         "data": None, 
            #         "status": "error", 
            #         "message": "No record found in Timesheet"
            #     }
    
            
            # Validate the data using our Pydantic model
            timesheet_data = TimesheetData(records=[
                TimesheetRecord(**record) for record in raw_data.get("records", [])
            ])

            # Check if records are empty

            # if not timesheet_data.records:
            #     logger.info("No record found in timesheet data")
            #     return {
            #         "data": None, 
            #         "status": "error", 
            #         "message": "No record found in Timesheet"
            #     }
                    
            logger.info(f"Extracted data: {timesheet_data}")
            # logger.info(f"Extracted test:{timesheet_data.records}")
            return {"data": timesheet_data.dict(), "status": "success"}

        except json.JSONDecodeError as e:
            logger.error(f"Error parsing JSON response: {str(e)}, response: {response_json}")
            return {"data": None, "status": "error", "message": f"Invalid JSON response: {str(e)}"}
        except Exception as e:
            logger.error(f"Error in extract_image_info: {str(e)}")
            return {"data": None, "status": "error", "message": str(e)} 