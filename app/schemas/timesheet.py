"""
Pydantic models for timesheet data validation.
"""

from datetime import date, datetime, time 
from pydantic import BaseModel, Field, validator
from typing import Dict, List, Optional, Union, Any


class TimesheetRecord(BaseModel):
    """Single timesheet record model."""
    date: str = Field(..., description="Date of the timesheet entry in YYYY-MM-DD format")
    time_in: Optional[str] = Field(None, description="Time in in HH:MM format")
    time_out: Optional[str] = Field(None, description="Time out in HH:MM format")
    lunch_timeout: Union[str, int] = Field(None, description="Lunch timeout in minutes or HH:MM format")
    total_hours: float = Field(None, description="Total hours worked")


class TimesheetData(BaseModel):
    """Model representing extracted timesheet data."""
    records: List[TimesheetRecord] = Field(default_factory=list, description="List of timesheet records")


class ValidationResult(BaseModel):
    # """Model for validation results."""
    # matches: bool
    # confidence: float
    # differences: Dict[str, Any]
    # explanation: str
    """Model for individual field validation results."""
    date_match: Optional[bool] = None
    time_in_match: Optional[bool] = None
    lunch_timeout_match: Optional[bool] = None
    time_out_match: Optional[bool] = None
    total_hours_match: Optional[bool] = None
    computed_vs_provided: Optional[bool] = None



class SingleRecordValidation(BaseModel):
    """Model for the validation result of a single timesheet record."""
    record: TimesheetRecord
    computed_hours: Optional[float] = None
    validation_results: Optional[ValidationResult] = None
    valid: bool
    message: str


class MultipleRecordsValidation(BaseModel):
    """Model for the validation of multiple timesheet records."""
    valid: bool
    message: str
    validation_results: List[SingleRecordValidation] = Field(default_factory=list)
    extracted_data: Optional[TimesheetData] = None


class UploadResponse(BaseModel):
    """Response model for the upload endpoint."""
    message: str
    image_data: Dict[str, Any]=None
    validation_results: Union[SingleRecordValidation, MultipleRecordsValidation] 
 

class TimesheetUpdate(BaseModel):
    date: str = Field(..., description="Date of the timesheet entry in YYYY-MM-DD format")
    lunch_timeout: Optional[str] = Field(None, example="30")
    time_in: Optional[str] = Field(None, example="09:00")
    time_out: Optional[str] = Field(None, example="17:00")
    total_hours: Optional[str] = Field(None, example="12")
    

    @validator('time_in', 'time_out')
    def validate_time_format(cls, v):
        if v is None:
            return v
        try:
            t, ampm = v.split(" ")
            hours, minutes = map(int, t.split(':'))
            if not (0 <= hours <= 23 and 0 <= minutes <= 59):
                raise ValueError("Invalid time format")
        except ValueError:
            raise ValueError("Time must be in HH:MM format")
        return v

    # @validator("total_hours")
    # def validate_total_hours(cls, h):
    #     try:
    #         hours, minutes = map(int, h.split(":"))
    #         if not (0 <= hours <= 23 and 0 <= minutes <= 59):
    #             raise ValueError("Invalid time format.")
    #     except ValueError:
    #         raise ValueError("Total hours must be in HH:MM format")
    #     return h
    
    @validator("date")
    def validate_date_format(cls, v):
        try:
            datetime.strptime(v, "%Y-%m-%d")
            return v
        except ValueError:
            raise ValueError("Date must be in YYYY-MM-DD format")