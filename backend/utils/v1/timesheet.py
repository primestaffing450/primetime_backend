import re
from typing import Optional, Dict
from fastapi import APIRouter, File, Form, HTTPException, UploadFile, Depends, Request
from app.utils.pdf_processing import convert_pdf_to_image
from datetime import datetime, timezone, timedelta
from app.core.database import db
from app.core.logging import logger
from app.core.config import settings
from pathlib import Path
import uuid
import os
from fastapi import HTTPException



def store_audit_log(user_id: str, extracted_data: dict, comparison_results: dict, additional_info: dict = None) -> str:
    """
    Stores an audit log entry with the given timesheet data and validation results into a separate collection.
    
    Args:
        user_id (str): The ID of the user.
        extracted_data (dict): Data extracted from the timesheet image.
        comparison_results (dict): The results of comparing the extracted data with stored entries.
        additional_info (dict, optional): Any extra information to log.
    
    Returns:
        str: The ID of the inserted document as a string.
    """
    # Build the audit log document.
    document = {
        "user_id": user_id,
        "timestamp": datetime.now(timezone.utc),
        "extracted_data": extracted_data,
        "comparison_results": comparison_results,
        "additional_info": additional_info or {}
    }
    
    # Insert the document into the "timesheet_audit" collection.
    result = db.db.timesheet_audit.insert_one(document)
    return str(result.inserted_id)


# Helper to normalize lunch_timeout to minutes as a float
def normalize_lunch_timeout(value: str) -> float:
    try:
        value = value.strip()
        if ":" in value:
            hours, minutes = map(int, value.split(':'))
            return hours * 60 + minutes
        else:
            num = float(value)
            # If the number is small (<=2), assume it's in hours; otherwise, assume minutes.
            return num * 60 if num <= 2 else num
    except Exception as e:
        logger.error(f"Error normalizing lunch timeout '{value}': {e}")
        return 0.0


def parse_time_format(time_str: str) -> str:
    """
    Convert any time format to 12-hour format with AM/PM.
    Accepts:
      - 24-hour format ("HH:MM" or "HH:MM:SS")
      - 12-hour format (with or without seconds, with or without AM/PM)
    """
    # List of possible time formats to try
    time_formats = [
        "%H:%M:%S",    # 24-hour format with seconds, e.g. "21:35:00"
        "%H:%M",       # 24-hour format without seconds, e.g. "21:35"
        "%I:%M:%S %p", # 12-hour format with seconds, e.g. "9:35:00 PM"
        "%I:%M %p",    # 12-hour format without seconds, e.g. "9:35 PM"
        "%I:%M"        # 12-hour format without AM/PM (assume AM), e.g. "9:35"
    ]
    
    for fmt in time_formats:
        try:
            time_obj = datetime.strptime(time_str.strip(), fmt)
            return time_obj.strftime("%I:%M %p")
        except ValueError:
            continue

    raise HTTPException(
        status_code=400,
        detail=f"Invalid time format: {time_str}. Use HH:MM or HH:MM AM/PM"
    )


# calculate week boundaries for specific monthly basis
# def get_week_boundaries_from_input(day_dates: list) -> (datetime, datetime):
#     """
#     Given a list of datetime objects (from user input), use the earliest date as the base
#     and compute week boundaries (Monday to Friday). If the computed Monday is before the
#     month or Friday is after the month of the base date, adjust to the first Monday or last Friday.
#     """
#     if not day_dates:
#         raise ValueError("No day dates provided.")
    
#     day_dates = [dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc) for dt in day_dates]
#     base_date = min(day_dates)

#     # Standard computation: Monday of base_date's week and the following Friday.
#     computed_monday = base_date - timedelta(days=base_date.weekday())
#     computed_friday = computed_monday + timedelta(days=4)
    
#     # Get the first Monday and last Friday of the base_date's month.
#     year, month = base_date.year, base_date.month
#     first_day = datetime(year, month, 1, tzinfo=base_date.tzinfo)
#     days_to_monday = (0 - first_day.weekday()) % 7  # Monday=0
#     first_monday = first_day + timedelta(days=days_to_monday)
    
#     # Last day of the month.
#     if month == 12:
#         next_month = datetime(year + 1, 1, 1, tzinfo=base_date.tzinfo)
#     else:
#         next_month = datetime(year, month + 1, 1, tzinfo=base_date.tzinfo)
#     last_day = next_month - timedelta(days=1)
#     days_from_friday = (last_day.weekday() - 4) % 7  # Friday=4
#     last_friday = last_day - timedelta(days=days_from_friday)
    
#     week_start = computed_monday if computed_monday.month == base_date.month else first_monday
#     week_end = computed_friday if computed_friday.month == base_date.month else last_friday
    
#     return week_start, week_end


# def get_week_boundaries_from_input(day_dates: list) -> (datetime, datetime):
#     """
#     Given a list of datetime objects, compute week boundaries (Monday to Friday) based on the earliest date,
#     allowing the week to span months.
#     """
#     if not day_dates:
#         raise ValueError("No day dates provided.")
    
#     # Ensure all dates are timezone-aware (UTC)
#     # day_dates = [dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc) for dt in day_dates]
    
#     # Find the earliest date
#     # base_date = min(day_dates)

#     # Get the local timezone.
#     # local_tz = get_localzone()

#     # Convert all dates to UTC; assume naïve datetimes are local.
#     # converted_dates = []
#     # for dt in day_dates:
#     #     # Localize if naive.
#     #     if dt.tzinfo is None:
#     #         dt = local_tz.localize(dt)
#     #     dt_utc = dt.astimezone(timezone.utc)
#     #     # Only include dates Monday(0) to Friday(4)
#     #     if dt_utc.weekday() >= 5:
#     #         # raise ValueError("Only Monday to Friday dates are allowed in weekly entry")
#     #         continue
#     #     converted_dates.append(dt_utc)
    
#     # # Find the earliest (now in UTC)
#     # base_date = min(converted_dates)

#     # if not converted_dates:
#     #     raise ValueError("No valid Monday-Friday dates provided for computing week boundaries.")
    
#     # Compute Monday of the base_date's week
#     computed_monday = base_date - timedelta(days=base_date.weekday())
#     # Compute Friday of that week
#     computed_friday = computed_monday + timedelta(days=4)
    
#     return computed_monday, computed_friday


def get_week_boundaries_from_input(day_dates: list) -> (datetime, datetime):
    """
    Given a list of datetime objects, compute week boundaries (Monday to Friday).
    If exactly two dates are provided and at least one is a Saturday or Sunday,
    return the next week's Monday and Friday. Otherwise, return the Monday and
    Friday of the earliest date's week. Boundaries are set to midnight UTC.
    """
    if not day_dates:
        raise ValueError("No day dates provided.")
    
    # Ensure all dates are timezone-aware (UTC)
    day_dates = [dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc) for dt in day_dates]
    
    # Find the earliest date
    base_date = min(day_dates)
    
    # Compute Monday of the base_date's week and set to midnight UTC
    monday = base_date - timedelta(days=base_date.weekday())
    monday = monday.replace(hour=0, minute=0, second=0, microsecond=0)
    
    # If exactly two dates and at least one is Saturday (5) or Sunday (6), shift to next week
    if any(date.weekday() in [5, 6] for date in day_dates):
        monday += timedelta(days=7)
    
    # Compute Friday of that week
    friday = monday + timedelta(days=4)
    
    return monday, friday




def get_first_and_last_weekdays_of_month(base_date: datetime):
    """
    Given a base date, return the first Monday and last Friday of that month.
    """
    year = base_date.year
    month = base_date.month

    # First day of the month
    first_day = datetime(year, month, 1, tzinfo=base_date.tzinfo)
    # Calculate first Monday (Monday = 0)
    days_to_monday = (0 - first_day.weekday()) % 7
    first_monday = first_day + timedelta(days=days_to_monday)

    # Last day of the month
    if month == 12:
        next_month = datetime(year + 1, 1, 1, tzinfo=base_date.tzinfo)
    else:
        next_month = datetime(year, month + 1, 1, tzinfo=base_date.tzinfo)
    last_day = next_month - timedelta(days=1)
    # Calculate last Friday (Friday = 4)
    days_from_friday = (last_day.weekday() - 4) % 7
    last_friday = last_day - timedelta(days=days_from_friday)

    return first_monday, last_friday


def get_week_boundaries_in_month(reference_date: datetime):
    """
    Calculate the week boundaries for the week containing reference_date,
    ensuring that the Monday (week_start) and Friday (week_end) lie within
    the same month as the reference_date.
    
    If the computed Monday is before the month, snap to the first Monday of the month.
    If the computed Friday is after the month, snap to the last Friday of the month.
    """
    # Standard calculation: Monday of reference_date's week and following Friday.
    computed_monday = reference_date - timedelta(days=reference_date.weekday())
    computed_friday = computed_monday + timedelta(days=4)
    
    # Get the first Monday and last Friday in the month.
    first_monday, last_friday = get_first_and_last_weekdays_of_month(reference_date)
    
    # Adjust if computed boundaries fall outside the month.
    if computed_monday.month != reference_date.month:
        week_start = first_monday
    else:
        week_start = computed_monday
        
    if computed_friday.month != reference_date.month:
        week_end = last_friday
    else:
        week_end = computed_friday
        
    return week_start, week_end

def populate_weekly_days(week_start: datetime, week_end: datetime, provided_days: dict):
    """
    Build a list of day entries for each day from week_start (Monday) to week_end (Friday).
    
    provided_days: dictionary keyed by date string ("YYYY-MM-DD") containing user-provided data.
    For missing days, placeholder values are inserted.
    """
    days = []
    current_day = week_start
    while current_day.date() <= week_end.date():
        day_key = current_day.strftime("%Y-%m-%d")
        if day_key in provided_days:
            entry = provided_days[day_key]
            # Ensure date is stored in ISO format.
            entry["date"] = current_day.isoformat()
            if "status" not in entry or not entry["status"]:
                entry["status"] = "not approved"
        else:
            # Default entry for missing day.
            entry = {
                "date": current_day.isoformat(),
                "time_in": None,
                "time_out": None,
                "lunch_timeout": 0,
                "total_hours": 0.0,
                "status": "missing"
            }
        days.append(entry)
        current_day += timedelta(days=1)
    return days


async def save_image(processed_bytes):
    UPLOAD_DIR = settings.IMAGE_DIR
    Path(UPLOAD_DIR).mkdir(parents=True, exist_ok=True)

    filename = f"{uuid.uuid4().hex}.png"
    file_path = os.path.join(UPLOAD_DIR, filename)
    try:
        with open(file_path, "wb") as f:
            f.write(processed_bytes)
    except Exception as e:
        logger.error(f"Error saving image file: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Error saving image file"
        )
    return file_path


def parse_form_data(form) -> Dict[str, Dict[str, str]]:
    """Parse form data to extract daily timesheet entries using regex pattern."""
    pattern = re.compile(r"\[(.*?)\]\[(.*?)\]")
    daily_entries = {}
    for key, value in form.multi_items():
        logger.debug(f"Processing form key: {key}, value: {value}")
        match = pattern.match(key)
        if match:
            date_key = match.group(1)
            field = match.group(2)
            if date_key not in daily_entries:
                daily_entries[date_key] = {"date": date_key}
            daily_entries[date_key][field] = value
    logger.info(f"Extracted daily entries: {daily_entries}")
    return daily_entries


async def handle_image_upload(image_file: Optional[UploadFile]) -> Optional[str]:
    """Handle image upload, process, and save it, returning the file path."""
    if image_file:
        file_bytes = await image_file.read()
        content_type = image_file.content_type
        if content_type.startswith("image/"):
            processed_bytes = file_bytes
        elif content_type == "application/pdf":
            processed_bytes = convert_pdf_to_image(file_bytes)
        else:
            raise HTTPException(status_code=400, detail="Invalid file type: must be image or PDF")
        file_path = await save_image(processed_bytes)
        logger.info(f"Image saved at: {file_path}")
        return file_path
    return None


async def handle_multiple_image_uploads(image_files: Optional[list[UploadFile]]) -> list[str]:
    """Handle multiple image uploads, process, and save them, returning the file paths."""
    file_paths = []
    
    if not image_files:
        return file_paths
    
    for idx, image_file in enumerate(image_files):
        if image_file and image_file.filename:  # Check if file is not empty
            try:
                file_bytes = await image_file.read()
                content_type = image_file.content_type
                
                if content_type.startswith("image/"):
                    processed_bytes = file_bytes
                elif content_type == "application/pdf":
                    processed_bytes = convert_pdf_to_image(file_bytes)
                else:
                    logger.warning(f"Skipping file {idx + 1}: Invalid file type {content_type}")
                    continue
                
                file_path = await save_image(processed_bytes)
                file_paths.append(file_path)
                logger.info(f"Image {idx + 1} saved at: {file_path}")
                
            except Exception as e:
                logger.error(f"Error processing file {idx + 1}: {str(e)}")
                # Continue processing other files even if one fails
                continue
    
    logger.info(f"Successfully processed {len(file_paths)} out of {len(image_files)} files")
    return file_paths


def validate_weekday_dates(entry_dates: list[datetime]):
    """
    Validate that none of the provided dates fall on a Saturday or Sunday.
    Raises an HTTPException if any date is on a weekend.
    
    Args:
        entry_dates (list[datetime]): List of datetime objects representing entry dates.
    
    Raises:
        HTTPException: If a date falls on a Saturday or Sunday, with status code 400 and a descriptive message.
    """
    for date in entry_dates:
        if date.weekday() >= 5:  # 5 = Saturday, 6 = Sunday
            raise HTTPException(
                status_code=400,
                detail=f"Entries for weekends (Saturday and Sunday) are not allowed. Invalid date: {date.strftime('%Y-%m-%d')}"
            )