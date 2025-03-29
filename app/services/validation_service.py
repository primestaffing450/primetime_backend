"""
Service for validating timesheet information.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Union, Any
from app.core.logging import logger
from app.schemas.timesheet import (
    TimesheetRecord,
    TimesheetData,
    ValidationResult,
    SingleRecordValidation,
    MultipleRecordsValidation
)


def validate_info(
    extracted_data_dict: Dict[str, Any],
    form_date: Optional[str] = None,
    form_time_in: Optional[str] = None,
    form_lunch_timeout: Optional[str] = None,
    form_time_out: Optional[str] = None,
    form_total_hours: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Validates extracted timesheet data against form inputs or internally validates each record.
    Can handle both single records and multiple records in the 'records' array.
    
    Args:
        extracted_data_dict: Dictionary containing extracted data
        form_date: Optional date from form input
        form_time_in: Optional time in from form input
        form_lunch_timeout: Optional lunch timeout from form input
        form_time_out: Optional time out from form input
        form_total_hours: Optional total hours from form input
        
    Returns:
        Dict containing validation results that can be converted to SingleRecordValidation
        or MultipleRecordsValidation
    """
    time_format = "%H:%M"
    
    # Get the extracted data, which may contain multiple records
    if "data" in extracted_data_dict:
        extracted_data = extracted_data_dict.get("data", {})
    else:
        extracted_data = extracted_data_dict  # Handle direct data input case
    
    logger.info(f"Validating extracted data: {extracted_data}")
    
    if not extracted_data:
        return {
            "valid": False,
            "message": "No data extracted from image"
        }
    
    try:
        # Check if we have multiple records
        if "records" in extracted_data and isinstance(extracted_data["records"], list):
            records = [TimesheetRecord(**record) for record in extracted_data["records"]]
            
            if all([form_date, form_time_in, form_lunch_timeout, form_time_out, form_total_hours]):
                # Collect validation results for all records
                validation_results = []
                overall_valid = True
                
                for record in records:
                    # Validate each record against form inputs
                    result = validate_single_record(
                        record,
                        form_date,
                        form_time_in,
                        form_lunch_timeout,
                        form_time_out,
                        form_total_hours
                    )
                    validation_results.append(result)
                    
                    # Update overall validity
                    if not result.get("valid", False):
                        overall_valid = False
                
                # Return combined results for all records
                return {
                    "valid": overall_valid,
                    "message": "All records validated successfully" if overall_valid else "Some records failed validation",
                    "validation_results": validation_results,
                    "extracted_data": {
                        "records": [record.dict() for record in records]
                    }
                }
            else:
                return {
                    "valid": False,
                    "message": "Form inputs are required for validation",
                    "extracted_data": extracted_data
                }
        else:
            # Handle single record case (legacy format)
            record = TimesheetRecord(**extracted_data)
            if all([form_date, form_time_in, form_lunch_timeout, form_time_out, form_total_hours]):
                return validate_single_record(
                    record,
                    form_date,
                    form_time_in,
                    form_lunch_timeout,
                    form_time_out,
                    form_total_hours
                )
            else:
                return {
                    "valid": False,
                    "message": "Form inputs are required for validation",
                    "extracted_data": extracted_data
                }
    
    except Exception as e:
        logger.error(f"Validation error: {str(e)}")
        return {
            "valid": False,
            "message": f"Validation error: {str(e)}",
            "extracted_data": extracted_data
        }


def validate_single_record(
    record: TimesheetRecord,
    form_date: str,
    form_time_in: str,
    form_lunch_timeout: str,
    form_time_out: str,
    form_total_hours: str,
) -> Dict[str, Any]:
    """
    Validates a single timesheet record against form inputs.
    
    Args:
        record: TimesheetRecord instance
        form_date: Date from form input
        form_time_in: Time in from form input
        form_lunch_timeout: Lunch timeout from form input
        form_time_out: Time out from form input
        form_total_hours: Total hours from form input
        
    Returns:
        Dict that can be converted to SingleRecordValidation
    """
    time_format = "%H:%M"
    
    try:
        # Parse input date
        input_date = datetime.strptime(form_date, "%Y-%m-%d").date()
        
        # Parse time values
        time_in_obj = datetime.strptime(form_time_in, time_format).time()
        time_out_obj = datetime.strptime(form_time_out, time_format).time()
        
        # Combine date and times
        dt_time_in = datetime.combine(input_date, time_in_obj)
        dt_time_out = datetime.combine(input_date, time_out_obj)
        
        # If time_out is earlier than time_in, assume the work period goes into the next day
        if dt_time_out < dt_time_in:
            dt_time_out += timedelta(days=1)
        
        # Process lunch timeout
        try:
            lunch_minutes = int(form_lunch_timeout)
        except ValueError:
            # If lunch_timeout is not an integer, it might be a time format
            try:
                lunch_obj = datetime.strptime(form_lunch_timeout, time_format).time()
                lunch_minutes = lunch_obj.hour * 60 + lunch_obj.minute
            except ValueError:
                raise ValueError(f"Cannot parse lunch timeout: {form_lunch_timeout}")
        
        # Compute working duration
        computed_duration = (dt_time_out - dt_time_in) - timedelta(minutes=lunch_minutes)
        computed_hours = computed_duration.total_seconds() / 3600.0
        
        # Parse provided total hours
        provided_total_hours = float(form_total_hours)
        
        # Validation results
        validation_results = ValidationResult(
            date_match=record.date == form_date,
            time_in_match=record.time_in == form_time_in,
            lunch_timeout_match=str(record.lunch_timeout) == str(form_lunch_timeout),
            time_out_match=record.time_out == form_time_out,
            total_hours_match=abs(float(record.total_hours) - provided_total_hours) < 0.1,
            computed_vs_provided=abs(computed_hours - provided_total_hours) < 0.1
        )
        
        all_match = all(
            value for value in validation_results.dict().values() 
            if value is not None
        )
        
        print('VAlidation record', validation_results.dict())
        
        return {
            "record": record.dict(),
            "computed_hours": round(computed_hours, 2),
            "validation_results": validation_results.dict(),
            "valid": all_match,
            "message": "All fields match" if all_match else "Some fields don't match"
        }
    
    except Exception as e:
        logger.error(f"Validation error for single record: {str(e)}")
        return {
            "valid": False,
            "message": f"Validation error: {str(e)}",
            "record": record.dict()
        }


def validate_record_internally(record: TimesheetRecord) -> Dict[str, Any]:
    """
    Validates a timesheet record internally without external comparison.
    
    Args:
        record: TimesheetRecord instance
        
    Returns:
        Dict that can be converted to SingleRecordValidation
    """
    time_format = "%H:%M"
    
    try:
        # Parse date
        try:
            record_date = datetime.strptime(record.date, "%Y-%m-%d").date()
        except ValueError as e:
            return {
                "valid": False,
                "message": f"Invalid date format: {str(e)}",
                "record": record.dict()
            }
        
        # Parse time values
        try:
            time_in_obj = datetime.strptime(record.time_in, time_format).time()
            time_out_obj = datetime.strptime(record.time_out, time_format).time()
        except ValueError as e:
            return {
                "valid": False,
                "message": f"Invalid time format: {str(e)}",
                "record": record.dict()
            }
        
        # Combine date and times
        dt_time_in = datetime.combine(record_date, time_in_obj)
        dt_time_out = datetime.combine(record_date, time_out_obj)
        
        # If time_out is earlier than time_in, assume the work period goes into the next day
        if dt_time_out < dt_time_in:
            dt_time_out += timedelta(days=1)
        
        # Process lunch timeout
        try:
            lunch_timeout = record.lunch_timeout
            if isinstance(lunch_timeout, (int, float)):
                lunch_minutes = int(lunch_timeout)
            else:
                try:
                    lunch_minutes = int(lunch_timeout)
                except ValueError:
                    # If lunch_timeout is not an integer, it might be a time format
                    lunch_obj = datetime.strptime(lunch_timeout, time_format).time()
                    lunch_minutes = lunch_obj.hour * 60 + lunch_obj.minute
        except Exception as e:
            return {
                "valid": False, 
                "message": f"Cannot parse lunch timeout: {str(e)}",
                "record": record.dict()
            }
        
        # Compute working duration
        computed_duration = (dt_time_out - dt_time_in) - timedelta(minutes=lunch_minutes)
        computed_hours = computed_duration.total_seconds() / 3600.0
        
        # Check if computed hours match provided hours
        hours_match = abs(computed_hours - float(record.total_hours)) < 0.1
        
        return {
            "record": record.dict(),
            "computed_hours": round(computed_hours, 2),
            "valid": hours_match,
            "message": "Computed hours match provided hours" if hours_match else "Computed hours don't match provided hours"
        }
    
    except Exception as e:
        logger.error(f"Internal validation error: {str(e)}")
        return {
            "valid": False,
            "message": f"Validation error: {str(e)}",
            "record": record.dict()
        } 