from bson import Binary
import os

from app.core.logging import logger

from app.core.database import db
from bson import ObjectId
from pathlib import Path

from app.services.notification_services import EmailServices
from app.services.openai_service import TimesheetImageExtractor
from app.services.validation_service import validate_info
from app.utils.timesheet import store_audit_log
from app.utils.pdf_processing import convert_pdf_to_image
from app.utils.image_processing import encode_image_to_base64
from fastapi import HTTPException, UploadFile
from app.schemas.auth import UserResponse
from app.utils.timesheet import save_image

from typing import Dict, Any, Optional, List
from datetime import datetime, timezone  # Add timezone since it's used in the code
from fastapi import HTTPException  # Add this import for error handling
from app.utils.timesheet import normalize_lunch_timeout, parse_time_format


def get_mismatch_details(record: Dict[str, Any], stored_day: Dict[str, Any]) -> List[str]:
    """
    Compare the record with the stored day and return a list of detail messages
    explaining any mismatches.
    """
    details = []
    try:
        # Convert extracted times (expected in 24-hour format "HH:MM")
        record_time_in = datetime.strptime(record["time_in"], "%H:%M").time()
        record_time_out = datetime.strptime(record["time_out"], "%H:%M").time()
        
        # Helper function to parse stored time (supports AM/PM or 24-hour)
        def parse_stored_time(t: str):
            if "AM" in t or "PM" in t:
                try:
                    return datetime.strptime(t, "%I:%M:%S %p").time()
                except ValueError:
                    return datetime.strptime(t, "%I:%M %p").time()
            else:
                return datetime.strptime(t, "%H:%M").time()
        
        stored_time_in = (parse_stored_time(stored_day["time_in"])
                          if isinstance(stored_day["time_in"], str)
                          else stored_day["time_in"].time())
        stored_time_out = (parse_stored_time(stored_day["time_out"])
                           if isinstance(stored_day["time_out"], str)
                           else stored_day["time_out"].time())
        
        # Normalize lunch timeout values
        record_lunch = normalize_lunch_timeout(str(record.get("lunch_timeout", "0")))
        stored_lunch = normalize_lunch_timeout(str(stored_day.get("lunch_timeout", "0")))
        
        # Compare total_hours with a tolerance
        record_hours = float(record.get("total_hours", 0))
        stored_hours = float(stored_day.get("total_hours", 0))
        hours_match = abs(record_hours - stored_hours) <= 0.01
        
        # Field-by-field checks
        if record_time_in != stored_time_in:
            details.append(f"time_in mismatch: extracted '{record['time_in']}' vs stored '{stored_day['time_in']}'")
        if record_time_out != stored_time_out:
            details.append(f"time_out mismatch: extracted '{record['time_out']}' vs stored '{stored_day['time_out']}'")
        if abs(record_lunch - stored_lunch) > 0.01:
            details.append(f"lunch_timeout mismatch: extracted '{record.get('lunch_timeout')}' vs stored '{stored_day.get('lunch_timeout')}'")
        if not hours_match:
            details.append(f"total_hours mismatch: extracted '{record.get('total_hours')}' vs stored '{stored_day.get('total_hours')}'")
    except Exception as e:
        details.append(f"Error comparing record: {str(e)}")
    return details



def compare_with_weekly_report(extracted_data: Dict[str, Any], previous_entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Compare extracted timesheet data (under key 'records') with stored weekly data.
    
    The stored data (previous_entries) is expected to be a list of weekly documents,
    each having a "days" key which is a list of day entries. Each day entry must contain:
       - date: an ISO string (e.g. "2025-03-20T00:00:00+00:00")
       - time_in: a string representing time (can be in 12- or 24-hour format)
       - time_out: same as above
       - lunch_timeout: numeric (minutes)
       - total_hours: numeric
       
    The extracted_data is expected to have a "records" key whose elements are dicts with:
       - date (in "YYYY-MM-DD")
       - time_in (expected in "HH:MM" format)
       - time_out (expected in "HH:MM" format)
       - lunch_timeout (string or numeric)
       - total_hours (numeric)
    
    Returns a dictionary containing:
       - valid: True if all records match; else False
       - message: Summary message
       - matches: list of matching record details
       - mismatched_entries: list of discrepancies per record
       - missing_entries: list of extracted image records not found in stored timesheet data
       - stored_missing_entries: list of stored days not found in Image
    """
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
    
    # Build a dictionary of stored days keyed by date string (YYYY-MM-DD)
    stored_days = {}
    for weekly_doc in previous_entries:
        days = weekly_doc.get("days", [])
        for day in days:
            try:
                # Assume stored day["date"] is in ISO format (e.g., "2025-03-20T00:00:00+00:00")
                # Extract the date part as "YYYY-MM-DD"
                date_str = day["date"][:10]
                stored_days[date_str] = day
            except Exception as e:
                logger.error(f"Error processing stored day entry: {e}")
    
    logger.info(f"Stored days for comparison: {stored_days}")
    
    # Process each extracted record
    extracted_dates = []

    for record in extracted_data.get("records", []):
        try:
            if not isinstance(record, dict) or "date" not in record:
                logger.error(f"Invalid record format: {record}")
                continue
            
            record_date = record.get("date")
            extracted_dates.append(record_date)
            if not record_date:
                logger.warning(f"Missing date in record: {record}")
                continue
            
            # If the extracted record's date exists in stored_days, compare the times
            if record_date in stored_days:
                stored_day = stored_days[record_date]
                details = get_mismatch_details(record, stored_day)
                
                if details:
                    comparison_results["mismatched_entries"].append({
                        "date": record_date,
                        "timesheet_data": record,
                        "stored_entry": {
                            "time_in": stored_day["time_in"],
                            "time_out": stored_day["time_out"],
                            "lunch_timeout": stored_day.get("lunch_timeout"),
                            "total_hours": stored_day.get("total_hours")
                        },
                        "details": details
                    })
                    comparison_results["valid"] = False
                    comparison_results["message"] = "Discrepancies found between extracted and stored Timesheet entries"
                else:
                    comparison_results["matches"].append({
                        "date": record_date,
                        "data": record
                    })
            else:
                # CHANGED: Added 'details' field for missing entries from stored data.
                comparison_results["missing_entries"].append({
                    "date": record_date,
                    "data": record,
                    "details": [f"Record for {record_date} is missing from stored Timesheet data."]
                })
                comparison_results["valid"] = False
                comparison_results["message"] = "Some records are missing from the stored Timesheet data"
        except Exception as proc_err:
            logger.error(f"Error processing record: {proc_err}")
            continue

    # CHANGED: For each stored day not present in extracted data, add to stored_missing_entries with details.
    for date_str, day_data in stored_days.items():
        if date_str not in extracted_dates:
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
    
    logger.info(f"Final comparison results: {comparison_results}")
    return comparison_results




async def validate_timesheet_image(image_path: str, current_user: UserResponse, week_data: dict) -> dict:
    """
    Validate timesheet image data against the provided week data using the stored image path.
    """
    logger.info(f"Processing image file at: {image_path}")
    try:
        # Read the image from disk
        with open(image_path, "rb") as f:
            processed_bytes = f.read()
    except Exception as e:
        logger.error(f"Error reading image file: {str(e)}")
        raise HTTPException(status_code=500, detail="Error reading image file")

    # Encode image to base64 for processing
    base64_image = encode_image_to_base64(processed_bytes)

    # Extract data from the image
    tie = TimesheetImageExtractor()
    extracted_result = tie.extract_image_info(
        base64_image=base64_image,
        ocr_text=""
    )
    logger.debug(f"Extracted Data: {extracted_result}")

    if extracted_result["status"] == "error":
        raise HTTPException(status_code=500, detail=extracted_result["message"])

    # Compare extracted data with week data
    comparison_results = compare_with_weekly_report(
        extracted_data=extracted_result["data"],
        previous_entries=[week_data]
    )

   # Build validation info for each day
    day_validation_info = {}
    for item in comparison_results.get("matches", []):
        date_str = item.get("data", {}).get("date")
        if date_str:
            day_validation_info[date_str] = "approved"
    for item in comparison_results.get("mismatched_entries", []):
        date_str = item.get("date")
        if date_str:
            day_validation_info[date_str] = "not approved"
    for item in comparison_results.get("missing_entries", []):
        date_str = item.get("date")
        if date_str:
            day_validation_info[date_str] = "missing from stored Timesheet data"
    for item in comparison_results.get("stored_missing_entries", []):
        date_str = item.get("date")
        if date_str:
            day_validation_info[date_str] = "missing from image"

    # Update week_data with validation status

    for day in week_data.get("days", []):
        day_key = day.get("date", "")[:10]  # Extract YYYY-MM-DD
        status_val = day_validation_info.get(day_key, "missing from image")  # Default to "missing from image"
        day["status"] = status_val
        day["validation_info"] = {"status": status_val, "details": None}

    # Update the database with validated data
    db.db.timesheet_entries.update_one(
        {"_id": ObjectId(week_data["_id"])},
        {"$set": {
            "days": week_data["days"],
            "validation_results": comparison_results,
            "is_validated": comparison_results["valid"],
            "updated_at": datetime.now(timezone.utc).isoformat()
        }}
    )

    # Store audit log
    audit_additional_info = {
        "note": "Weekly timesheet validation",
        "week_data": week_data,
        "image_path": image_path,
        "content_type": "image/png"
    }
    audit_id = store_audit_log(
        user_id=str(current_user.id),
        extracted_data=extracted_result["data"],
        comparison_results=comparison_results,
        additional_info=audit_additional_info
    )
    logger.info(f"Audit log stored with ID: {audit_id}")

    return {
        "message": "File processed and validated successfully",
        "image_data": extracted_result,
        "validation_results": comparison_results,
        "week_data": week_data
    }