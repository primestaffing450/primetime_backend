"""
Pydantic models for timesheet data validation.
"""

from datetime import date, time
from pydantic import BaseModel, Field
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