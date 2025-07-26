from typing import Any, List, Optional, Dict
from datetime import datetime
from pydantic import BaseModel
from app.schemas.timesheet import TimesheetRecord

class UserListResponse(BaseModel):
    message: str
    users: List[dict]

class TimesheetResponse(BaseModel):
    user_id: str
    date: datetime
    time_in: datetime
    time_out: datetime
    lunch_timeout: str
    total_hours: float
    is_approved: bool
    status: str
    created_at: datetime
    updated_at: datetime

# class TimesheetListResponse(BaseModel):
#     message: str
#     timesheets: List[TimesheetResponse]


class TimesheetListResponse(BaseModel):
    message: str
    timesheets: List[Dict[str, Any]]
    total_count: Optional[int] = 0
    date_range: Optional[Dict[str, str]] = None