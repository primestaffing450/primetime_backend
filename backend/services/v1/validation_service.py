"""
Service for validating timesheet information using AI-based validation.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Union, Any
import json
from app.core.logging import logger
from app.core.config import settings
from app.schemas.timesheet import (
    TimesheetRecord,
    TimesheetData,
    ValidationResult,
    SingleRecordValidation,
    MultipleRecordsValidation
)
from app.services.openai_service import TimesheetImageExtractor

# AI Validation Prompt for flexible comparison
AI_VALIDATION_PROMPT = """You are a helpful assistant that validates timesheet information with high flexibility.
Your task is to compare two timesheet records and determine if they match, considering:

1. Dates can be in ANY format (MM-DD-YYYY, DD-MM-YYYY, YYYY-MM-DD, etc.) and should be considered matching if they represent the same day
2. Rule out the year while comparing the dates for now if the year is not present in the date consider it the current ongoing year only not nay previous year.
3. Times can be in ANY format (12-hour or 24-hour) and should be considered matching if they represent the same time
4. Lunch timeouts can be in ANY format (minutes, HH:MM, etc.) and should be considered matching if they represent the same duration
5. Total hours can have small variations (e.g., 7.5 vs 7.50) and should be considered matching if they're within 0.1 hours
6. Be EXTREMELY flexible with time formats and small variations
7. If dates are in different formats but represent the same day, consider them matching
8. If times are in different formats but represent the same time, consider them matching
9. If lunch duration is in different formats but represents the same duration, consider them matching
10. If you are having any doubt with slash in between date and month so consider one time / as slash only till the time there are no // identified consider that as a slash.

Compare the following records and determine if they match:
Extracted Record: {extracted_record}
Form Record: {form_record}

Return your response as a JSON object with:
{
    "matches": true/false,
    "confidence": 0-1,
    "differences": {
        "date": "explanation if different",
        "time_in": "explanation if different",
        "time_out": "explanation if different",
        "lunch_timeout": "explanation if different",
        "total_hours": "explanation if different"
    },
    "explanation": "Detailed explanation of why the records match or don't match"
}
"""

def normalize_date(date_str: str) -> str:
    """
    Normalize any date format to YYYY-MM-DD.
    Handles multiple date formats and returns None if invalid.
    """
    if not date_str:
        return None
        
    # Common date formats to try
    date_formats = [
        "%Y-%m-%d",  # YYYY-MM-DD
        "%m-%d-%Y",  # MM-DD-YYYY
        "%d-%m-%Y",  # DD-MM-YYYY
        "%Y/%m/%d",  # YYYY/MM/DD
        "%m/%d/%Y",  # MM/DD/YYYY
        "%d/%m/%Y",  # DD/MM/YYYY
        "%m.%d.%Y",  # MM.DD.YYYY
        "%d.%m.%Y",  # DD.MM.YYYY
    ]
    
    # Try each format
    for fmt in date_formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    
    # If all formats fail, try to extract date components
    try:
        # Remove any non-numeric characters except for separators
        cleaned = ''.join(c for c in date_str if c.isdigit() or c in '-/')
        parts = [p for p in cleaned.split('-') if p]
        if len(parts) == 3:
            # Try to determine the format based on the values
            year = next((p for p in parts if len(p) == 4), None)
            if year:
                # If we found a 4-digit year, use it
                other_parts = [p for p in parts if p != year]
                if len(other_parts) == 2:
                    # Assume first part is month, second is day
                    return f"{year}-{other_parts[0].zfill(2)}-{other_parts[1].zfill(2)}"
    except Exception:
        pass
    
    return None

def validate_with_ai(
    extracted_record: Dict[str, Any],
    form_record: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Validates timesheet records using AI for flexible comparison.
    """
    try:
        logger.info("Starting AI validation")
        logger.info(f"Extracted record: {json.dumps(extracted_record, indent=2)}")
        logger.info(f"Form record: {json.dumps(form_record, indent=2)}")
        
        # Initialize OpenAI client
        extractor = TimesheetImageExtractor()
        
        # Normalize dates before comparison
        if "date" in extracted_record:
            extracted_date = normalize_date(extracted_record["date"])
            if extracted_date:
                extracted_record["date"] = extracted_date
                
        if "date" in form_record:
            form_date = normalize_date(form_record["date"])
            if form_date:
                form_record["date"] = form_date
        
        logger.info(f"Normalized extracted record: {json.dumps(extracted_record, indent=2)}")
        logger.info(f"Normalized form record: {json.dumps(form_record, indent=2)}")
        
        # Prepare the prompt
        prompt = AI_VALIDATION_PROMPT.format(
            extracted_record=json.dumps(extracted_record, indent=2),
            form_record=json.dumps(form_record, indent=2)
        )
        
        # Get AI validation
        response = extractor.openai_client.chat.completions.create(
            model=settings.MODEL_NAME,
            messages=[
                {"role": "system", "content": "You are a helpful assistant that validates timesheet information with high flexibility."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            response_format={"type": "json_object"}
        )
        
        # Parse response
        validation_result = json.loads(response.choices[0].message.content)
        logger.info(f"AI validation result: {json.dumps(validation_result, indent=2)}")
        
        # Consider matches with high confidence as valid
        is_valid = validation_result.get("matches", False) and validation_result.get("confidence", 0) > 0.7
        
        return {
            "valid": is_valid,
            "confidence": validation_result.get("confidence", 0),
            "differences": validation_result.get("differences", {}),
            "explanation": validation_result.get("explanation", ""),
            "message": "Records match" if is_valid else "Records don't match",
            "extracted_record": extracted_record,
            "form_record": form_record
        }
        
    except Exception as e:
        logger.error(f"AI validation error: {str(e)}")
        return {
            "valid": False,
            "message": f"AI validation error: {str(e)}",
            "extracted_record": extracted_record,
            "form_record": form_record
        }

def validate_info(
    extracted_data_dict: Dict[str, Any],
    form_date: Optional[str] = None,
    form_time_in: Optional[str] = None,
    form_lunch_timeout: Optional[str] = None,
    form_time_out: Optional[str] = None,
    form_total_hours: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Validates extracted timesheet data against form inputs using AI-based validation.
    """
    if "data" in extracted_data_dict:
        extracted_data = extracted_data_dict.get("data", {})
    else:
        extracted_data = extracted_data_dict
    
    logger.info(f"Validating extracted data: {extracted_data}")
    
    if not extracted_data:
        return {
            "valid": False,
            "message": "No data extracted from image"
        }
    
    try:
        # Handle multiple records
        if "records" in extracted_data and isinstance(extracted_data["records"], list):
            validation_results = []
            overall_valid = True
            
            for record in extracted_data["records"]:
                # Prepare records for AI validation
                extracted_record = {
                    "date": record.get("date", ""),
                    "time_in": record.get("time_in", ""),
                    "time_out": record.get("time_out", ""),
                    "lunch_timeout": str(record.get("lunch_timeout", "")),
                    "total_hours": str(record.get("total_hours", ""))
                }
                
                form_record = {
                    "date": form_date,
                    "time_in": form_time_in,
                    "time_out": form_time_out,
                    "lunch_timeout": form_lunch_timeout,
                    "total_hours": form_total_hours
                }
                
                # Use AI validation
                result = validate_with_ai(extracted_record, form_record)
                validation_results.append(result)
                    
                if not result["valid"]:
                        overall_valid = False
                
                return {
                    "valid": overall_valid,
                    "message": "All records validated successfully" if overall_valid else "Some records failed validation",
                    "validation_results": validation_results,
                    "extracted_data": extracted_data
                }
        else:
            # Handle single record
            extracted_record = {
                "date": extracted_data.get("date", ""),
                "time_in": extracted_data.get("time_in", ""),
                "time_out": extracted_data.get("time_out", ""),
                "lunch_timeout": str(extracted_data.get("lunch_timeout", "")),
                "total_hours": str(extracted_data.get("total_hours", ""))
            }
            
            form_record = {
                "date": form_date,
                "time_in": form_time_in,
                "time_out": form_time_out,
                "lunch_timeout": form_lunch_timeout,
                "total_hours": form_total_hours
            }
            
            return validate_with_ai(extracted_record, form_record)
    
    except Exception as e:
        logger.error(f"Validation error: {str(e)}")
        return {
            "valid": False,
            "message": f"Validation error: {str(e)}",
            "extracted_data": extracted_data
        }

def compare_with_weekly_report(extracted_data: Dict[str, Any], previous_entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Compare extracted timesheet data with stored weekly data using AI-based validation.
    """
    logger.info("Starting weekly report comparison")
    logger.info(f"Extracted data: {json.dumps(extracted_data, indent=2)}")
    logger.info(f"Previous entries: {json.dumps(previous_entries, indent=2)}")
    
    comparison_results = {
        "valid": True,
        "message": "Validation completed",
        "matches": [],
        "mismatched_entries": [],
        "missing_entries": [],
        "stored_missing_entries": []
    }
    
    if not extracted_data or 'records' not in extracted_data:
        logger.error("No records found in extracted data")
        return {
            "valid": False,
            "message": "No data extracted from image",
            "matches": [],
            "mismatched_entries": [],
            "missing_entries": [],
            "stored_missing_entries": []
        }
    
    # Build a dictionary of stored days keyed by normalized date string (YYYY-MM-DD)
    stored_days = {}
    for weekly_doc in previous_entries:
        days = weekly_doc.get("days", [])
        for day in days:
            try:
                # Normalize stored date
                stored_date = day["date"][:10]  # Extract YYYY-MM-DD from ISO format
                stored_days[stored_date] = day
                logger.info(f"Added stored day: {stored_date} -> {json.dumps(day, indent=2)}")
            except Exception as e:
                logger.error(f"Error processing stored day entry: {e}")
    
    logger.info(f"Stored days for comparison: {json.dumps(stored_days, indent=2)}")
    
    # Process each extracted record
    extracted_dates = []
    for record in extracted_data.get("records", []):
        try:
            if not isinstance(record, dict) or "date" not in record:
                logger.error(f"Invalid record format: {record}")
                continue
            
            record_date = record.get("date")
            if not record_date:
                logger.warning(f"Missing date in record: {record}")
                continue

            logger.info(f"Processing record with date: {record_date}")
            logger.info(f"Full record: {json.dumps(record, indent=2)}")

            # Normalize the extracted date
            formatted_record_date = normalize_date(record_date)
            if not formatted_record_date:
                logger.error(f"Could not normalize date: {record_date}")
                continue

            logger.info(f"Normalized date: {formatted_record_date}")
            extracted_dates.append(formatted_record_date)
            
            # Compare with stored data using AI
            if formatted_record_date in stored_days:
                stored_day = stored_days[formatted_record_date]
                logger.info(f"Found matching stored day: {json.dumps(stored_day, indent=2)}")
                
                comparison = validate_with_ai(record, stored_day)
                logger.info(f"AI comparison result: {json.dumps(comparison, indent=2)}")
                
                if comparison["valid"]:
                    comparison_results["matches"].append({
                        "date": record_date,
                        "data": record
                    })
                else:
                    comparison_results["mismatched_entries"].append({
                        "date": record_date,
                        "timesheet_data": record,
                        "stored_entry": stored_day,
                        "details": comparison["differences"],
                        "explanation": comparison["explanation"]
                    })
                    comparison_results["valid"] = False
            else:
                logger.warning(f"No matching stored day found for {formatted_record_date}")
                comparison_results["missing_entries"].append({
                    "date": record_date,
                    "data": record,
                    "details": [f"Record for {record_date} is missing from stored Timesheet data."]
                })
                comparison_results["valid"] = False
                
        except Exception as e:
            logger.error(f"Error processing record: {str(e)}")
            continue

    # Check for stored days not present in extracted data
    logger.info(f"Checking for missing stored days. Extracted dates: {extracted_dates}")
    for date_str, day_data in stored_days.items():
        if date_str not in extracted_dates:
            logger.warning(f"Stored day {date_str} not found in extracted dates")
            comparison_results["stored_missing_entries"].append({
                "date": date_str,
                "data": day_data,
                "details": [f"Stored day for {date_str} is missing from extracted image data."]
            })
            comparison_results["valid"] = False
            if "missing from image" not in comparison_results["message"]:
                if comparison_results["message"] == "Validation completed":
                    comparison_results["message"] = "Some days in stored data are missing from the image"
                else:
                    comparison_results["message"] += ", some days in stored data are missing from the image"
    
    logger.info(f"Final comparison results: {json.dumps(comparison_results, indent=2)}")
    return comparison_results 