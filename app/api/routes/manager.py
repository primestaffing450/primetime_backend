import os
from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from fastapi_jwt_auth import AuthJWT

import base64
from app.core.database import db
from app.utils.managers import merge_audit_info_into_week
from app.core.logging import logger
from app.core.security import verify_manager_role
from app.models.user import RoleUpdate
from app.schemas.auth import UserRole
from app.schemas.manager import (
    UserListResponse,
)
from app.schemas.auth import UserResponse
from app.schemas.timesheet import TimesheetUpdate
from app.services.notification_services import EmailServices

router = APIRouter()


def process_and_store_image(audit_id: str, processed_bytes: bytes, content_type: str = "image/png"):
    # Convert to base64 and store in your DB (or cache)
    b64_str = base64.b64encode(processed_bytes).decode("utf-8")
    data_uri = f"data:{content_type};base64,{b64_str}"
    # Update the audit log in the DB with the data_uri
    db.db.timesheet_audit.update_one(
        {"_id": ObjectId(audit_id)},
        {"$set": {"additional_info.image_data": data_uri}}
    )


@router.get("/users", response_model=UserListResponse, tags=["users"])
async def get_all_users(
    current_user=Depends(verify_manager_role)
):
    """Get all users"""
    try:
        # Get all users
        users = db.db.users.find().to_list(None)
    
        return UserListResponse(
            message="Users retrieved successfully",
            users=[{**user, "_id": str(user["_id"])} for user in users]
        )

    except Exception as e:
        logger.error(f"Error fetching users: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error fetching users"
        )


@router.put('/users/{user_id}/role', response_model=dict)
async def update_user_role(
    user_id: str, 
    role_update: RoleUpdate, 
    current_user=Depends(verify_manager_role)
):
    """Update user role"""
    try:

        if role_update.role not in [role.value for role in UserRole]:
            raise HTTPException(status_code=400, detail="Invalid role")

        # Prevent self-role modification
        if user_id == str(current_user.id):
            raise HTTPException(
                status_code=400, 
                detail="Cannot modify your own role"
            )

        result = db.db.users.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": {
                "role": role_update.role,
                "updated_at": datetime.now()
            }}
        )

        if result.modified_count == 0:
            raise HTTPException(
                status_code=404, 
                detail="User not found or role not updated"
            )
        
        return {"message": "User role updated successfully"}

    except Exception as e:
        logger.error(f"Error updating user role: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error updating user role"
        )


@router.put('/timesheets/{timesheet_id}/approve', response_model=dict)
async def approve_timesheet(
    timesheet_id: str,
    current_user=Depends(verify_manager_role)

):
    """Approve a timesheet entry"""
    try:
        # First check if timesheet exists and its current status
        timesheet = db.db.timesheet_entries.find_one({"_id": ObjectId(timesheet_id)})
        
        if not timesheet:
            raise HTTPException(
                status_code=404,
                detail="Timesheet entry not found"
            )

        # Check if timesheet is already approvee
        if timesheet.get("is_approved"):
            raise HTTPException(
                status_code=400,
                detail={
                    "message": "Timesheet is already approved",
                    "approved_by": timesheet.get("approver_name"),
                    "approved_at": timesheet.get("approved_at").isoformat() if timesheet.get("approved_at") else None
                }
            )
        # Update the timesheet
        result = db.db.timesheet_entries.update_one(
            {"_id": ObjectId(timesheet_id)},
            {
                "$set": {
                    "is_approved": True,
                    "status": "approved",
                    "approved_by": str(current_user.id),
                    "approved_at": datetime.now(timezone.utc),
                    "updated_at": datetime.now(timezone.utc),
                    "approver_name": current_user.full_name
                }
            }
        )

         # Send approval notification

        email_service = EmailServices()
        await email_service.send_timesheet_approval_notification(
            user_id=str(timesheet["user_id"]),
            timesheet_id=timesheet_id,
            approved_by=current_user.full_name,
            timesheet_data=timesheet
        )
            
        return {
            "message": "Timesheet approved successfully",
            "timesheet_id": timesheet_id,
            "approved_by": current_user.full_name,
            "approved_at": datetime.now(timezone.utc).isoformat()
        }

    except HTTPException as he:
        # Re-raise HTTP exceptions
        raise he

    except Exception as e:
        logger.error(f"Error approving timesheet: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error approving timesheet"
        )

""" week data from the timesheet entry"""
@router.get("/timesheets/monthly/{user_id}", tags=["timesheets"])
async def get_monthly_timesheets(
    user_id: str,
    year: Optional[int] = Query(None, description="Year for timesheet entries"),
    month: Optional[int] = Query(None, description="Month for timesheet entries (1-12)"),
    current_user=Depends(verify_manager_role)
):
    """
    Get validated timesheet entries for a specific month (current month if not provided) from audit logs.
    The response returns:
      - user_info
      - month_info (year, month, start_date, end_date)
      - weekly_summaries: a list of summaries for each validated week in the month.
          Each summary includes the week_id, week_start, week_end, and overall validation_status.
      - summary: overall counts.
    
    The endpoint accepts optional query parameters 'year' and 'month'.
    """
    logger.info(f"Fetching monthly timesheets for user_id: {user_id}")
    try:
        current_date = datetime.now(timezone.utc)
        year = year or current_date.year
        month = month or current_date.month

        # Validate user exists.
        user = db.db.users.find_one({"_id": ObjectId(user_id)})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        if not (1 <= month <= 12):
            raise HTTPException(status_code=400, detail="Invalid month")
        if not (1900 <= year <= 2100):
            raise HTTPException(status_code=400, detail="Invalid year")

        # Calculate start and end date of the month.
        start_date = datetime(year, month, 1, tzinfo=timezone.utc)
        if month == 12:
            end_date = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
        else:
            end_date = datetime(year, month + 1, 1, tzinfo=timezone.utc)

        # Convert to ISO strings
        start_date_str = start_date.isoformat()
        end_date_str = end_date.isoformat()

        # Query audit logs for validated weeks where week_start is within the selected month
        # audit_query = {
        #     "user_id": user_id,
        #     "additional_info.week_data.week_start": {"$gte": start_date_str, "$lt": end_date_str}
        # }


        audit_query = {
            "user_id": user_id,
            "additional_info.week_data.week_end": {"$gt": start_date_str},
            "additional_info.week_data.week_start": {"$lt": end_date_str}
        }


        audit_logs = list(db.db.timesheet_audit.find(audit_query).sort("timestamp", -1))
        logger.info(f"Found {len(audit_logs)} audit logs for weeks starting in the month")

        # Group by week_id and take the most recent validation for each week
        audit_by_week = {}
        for audit in audit_logs:
            try:
                week_id = str(audit["additional_info"]["week_data"]["_id"])
                if week_id not in audit_by_week or audit["timestamp"] > audit_by_week[week_id]["timestamp"]:
                    audit_by_week[week_id] = audit
            except Exception as e:
                logger.error(f"Error processing audit log for grouping: {e}")


        # Add current week details
        from datetime import timedelta
        current_date = datetime.now(timezone.utc)
        current_monday = current_date - timedelta(days=current_date.weekday())
        current_week_start_str = current_monday.isoformat()

        # Check if current week is already in the audit logs.
        if not any(audit["additional_info"]["week_data"]["week_start"] == current_week_start_str 
                   for audit in audit_by_week.values()):
            # Attempt to fetch the current week audit log.
            current_week_audit = db.db.timesheet_audit.find_one({
                "user_id": user_id,
                "additional_info.week_data.week_start": current_week_start_str
            })
            if current_week_audit:
                week_id = str(current_week_audit["additional_info"]["week_data"]["_id"])
                audit_by_week[week_id] = current_week_audit
                logger.info("Added current week audit log from audit collection.")
            else:
                logger.info("Current week audit log not found in audit logs.")

        # Build weekly summaries
        weekly_summaries = []
        for week_id, audit_log in audit_by_week.items():
            week_data = audit_log["additional_info"]["week_data"]
            comparison_results = audit_log.get("comparison_results", {"valid": False})
            last_validated_at = audit_log["timestamp"].isoformat() if isinstance(audit_log["timestamp"], datetime) else str(audit_log["timestamp"])

            summary_obj = {
                "week_id": week_id,
                "week_start": week_data["week_start"],
                "week_end": week_data["week_end"],
                "validation_status": comparison_results.get("valid", False),
                "last_validated_at": last_validated_at
            }
            weekly_summaries.append(summary_obj)

        overall_summary = {
            "total_timesheets": len(weekly_summaries),  # Count of validated weeks
            "total_audits": len(audit_logs)
        }

        return {
            "user_info": {
                "id": str(user["_id"]),
                "username": user["username"],
                "full_name": user["full_name"],
                "email": user["email"]
            },
            "month_info": {
                "year": year,
                "month": month,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat()
            },
            "weekly_summaries": weekly_summaries,
            "summary": overall_summary
        }

    except Exception as e:
        logger.error(f"Error fetching monthly timesheets: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error fetching monthly timesheets"
        )


@router.get("/timesheets/weekly/{week_id}", tags=["timesheets"])
async def get_weekly_timesheet(
    week_id: str,
    current_user=Depends(verify_manager_role)
):
    """
    Retrieve a specific weekly timesheet entry using its _id.
    Also returns the overall validation status and image for that week.
    
    The response includes:
      - week_data: Contains week_id, week_start, week_end, and a list of day entries.
         Each day entry will include its "status" and a "validation_info_status" field (a simple string).
      - overall_validation_status: Overall validation status from the audit log.
      - image: The image file path (or URL) stored in the audit log.
      
    This endpoint does not update the database; it only merges stored data for the response.
    """
    try:
        # Fetch the weekly timesheet document
        weekly_entry = db.db.timesheet_entries.find_one({"_id": ObjectId(week_id)})
        
        if not weekly_entry:
            raise HTTPException(status_code=404, detail="Weekly timesheet entry not found")
        weekly_entry["_id"] = str(weekly_entry["_id"])
        
        # Prepare week_data with actual timesheet data
        week_data = {
            "week_id": weekly_entry["_id"],
            "week_start": weekly_entry["week_start"],
            "week_end": weekly_entry["week_end"],
            "days": weekly_entry.get("days", []),  # Use actual timesheet data
        }
        
        # Get audit data for validation info
        audit_query = {
            "user_id": weekly_entry["user_id"],
            "additional_info.week_data._id": week_id
        }
        audit_logs = list(db.db.timesheet_audit.find(audit_query).sort("timestamp", -1))
        print("$$$$$")
        
        if audit_logs:
            most_recent_audit = audit_logs[0]
            most_recent_audit["_id"] = str(most_recent_audit["_id"])
            comparison_results = most_recent_audit.get("comparison_results", {})
            image = most_recent_audit.get("additional_info", {}).get("image_path")
            overall_validation_status = comparison_results.get("valid", False)
            
            # Process validation info
            mismatched = {entry["date"]: entry for entry in comparison_results.get("mismatched_entries", [])}
            missing = {entry["date"]: entry for entry in comparison_results.get("missing_entries", [])}
            stored_missing = {entry["date"]: entry for entry in comparison_results.get("stored_missing_entries", [])}
            
            # Add validation info to each day
            for day in week_data["days"]:
                day_date = day.get("date", "")[:10]
                ai_status = "approved"
                reason = "All fields match."
                
                if day_date in mismatched:
                    ai_status = "not approved"
                    reason = "; ".join(mismatched[day_date].get("details", []))
                elif day_date in missing:
                    ai_status = "missing from stored data"
                    reason = "; ".join(missing[day_date].get("details", []))
                elif day_date in stored_missing:
                    ai_status = "missing from image"
                    reason = "; ".join(stored_missing[day_date].get("details", []))
                
                day["ai_validation_info"] = {"status": ai_status, "reason": reason}
        else:
            image = None
            overall_validation_status = False
            
        return {
            "week_data": week_data,
            "image": image,
            "overall_validation_status": overall_validation_status,
        }
        
    except HTTPException as he:
        logger.error(f"HTTP Exception: {str(he)}")
        raise he
    except Exception as e:
        logger.error(f"Error fetching weekly timesheet: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error fetching weekly timesheet"
        )


@router.get("/timesheets/weekly/export/all", tags=["timesheets"])
async def export_all_weekly_timesheets_json(
    start_date: Optional[str] = Query(None, description="ISO start date for filtering weekly timesheets"),
    end_date: Optional[str] = Query(None, description="ISO end date for filtering weekly timesheets"),
    current_user=Depends(verify_manager_role)
):
    """
    Export weekly timesheet data for all users as JSON.
    
    For each weekly timesheet, the export row (as a dictionary) contains:
      - Date Submitted
      - Name
      - Email
      - Date Worked
      - Time In
      - Time Out
      - Lunch
      - Total Daily Hours
      - Approve/Reject
      - AI Discrepancy Detected (Y/N)
      
    The response returns a JSON object with a single key "data" containing an array of rows.
    Export last week's timesheet data for all users as JSON.
    If no dates are provided, it defaults to the last full week (Monday–Sunday).
    """
    now = datetime.now(timezone.utc)
    last_monday = (now - timedelta(days=now.weekday() + 7)).replace(hour=0, minute=0, second=0, microsecond=0)
    last_friday = last_monday + timedelta(days=4)
    
    # Query for last week's Monday to Friday data only
    query = {
        "week_start": last_monday.isoformat(),
        "week_end": last_friday.isoformat()
    }
    
    weekly_entries = list(db.db.timesheet_entries.find(query).sort("week_start", 1))
    if not weekly_entries:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No weekly timesheets found")
    try:
        export_rows = []
        for weekly_entry in weekly_entries:
            weekly_entry["_id"] = str(weekly_entry["_id"])
            submitter = db.db.users.find_one({"_id": ObjectId(weekly_entry["user_id"])})
            if not submitter:
                continue

            submitter_name = submitter.get("full_name")
            submitter_email = submitter.get("email")
            print(submitter_email)
            audit_query = {
                "user_id": weekly_entry["user_id"],
                "additional_info.week_data._id": weekly_entry["_id"]
            }
            audit_logs = list(db.db.timesheet_audit.find(audit_query).sort("timestamp", -1))
            formatted_audit_logs = [{"_id": str(al["_id"]), **al} for al in audit_logs]
            print(audit_logs)
            week_data = {
                "week_id": weekly_entry["_id"],
                "week_start": weekly_entry["week_start"],
                "week_end": weekly_entry["week_end"],
                "days": weekly_entry.get("days", [])
            }

            week_data = merge_audit_info_into_week(week_data, formatted_audit_logs)
            overall_validation_status = formatted_audit_logs[0].get("comparison_results", {}).get("valid", False) if formatted_audit_logs else False
            ai_discrepancy = "Y" if not overall_validation_status else "N"
            date_submitted = weekly_entry.get("created_at", "")
            image_path = weekly_entry.get("image_path", "")
            if image_path:
                image_path = os.getenv("BACKEND_URL") + f"/{image_path}"
            
            for day in week_data["days"]:
                row = {
                    "date_submitted": date_submitted,
                    "image_path": image_path,
                    "name": submitter_name,
                    "email": submitter_email,
                    "date_worked": day.get("date"),
                    "time_in": day.get("time_in"),
                    "time_out": day.get("time_out"),
                    "lunch": day.get("lunch_timeout"),
                    "total_daily_hours": day.get("total_hours"),
                    "notes": day.get("notes", ""),
                    "approve_reject": "approved" if day.get("status") == "approved" else "reject",
                    "ai_Discrepancy_detected": ai_discrepancy
                }
                export_rows.append(row)
            
        logger.info(f"Exported {len(export_rows)} rows for last week's timesheets")
        return JSONResponse(content={"rows": export_rows})
    except Exception as e:
        logger.error(f"Error exporting weekly timesheets: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error exporting weekly timesheets")


@router.delete("/timesheets/weekly/{week_id}", tags=["timesheets"])
async def delete_weekly_timesheet(
    week_id: str,
    current_user=Depends(verify_manager_role)
):
    """
    Delete a weekly timesheet record from the database.
    Only managers can delete timesheet records to allow users to resubmit.
    
    This endpoint:
    - Deletes the timesheet entry from timesheet_entries collection
    - Deletes associated audit logs from timesheet_audit collection
    - Removes the associated image file if it exists
    - Returns confirmation of deletion
    """
    try:
        logger.info(f"Manager {current_user.full_name} attempting to delete weekly timesheet: {week_id}")
        
        # First check if timesheet exists
        timesheet = db.db.timesheet_entries.find_one({"_id": ObjectId(week_id)})
        if not timesheet:
            raise HTTPException(
                status_code=404,
                detail="Weekly timesheet entry not found"
            )
        
        # Get user information for logging
        user = db.db.users.find_one({"_id": ObjectId(timesheet["user_id"])})
        user_name = user.get("full_name", "Unknown User") if user else "Unknown User"
        
        # Store image path for deletion
        image_path = timesheet.get("image_path")
        
        # Delete the timesheet entry
        delete_result = db.db.timesheet_entries.delete_one({"_id": ObjectId(week_id)})
        
        if delete_result.deleted_count == 0:
            raise HTTPException(
                status_code=404,
                detail="Failed to delete timesheet entry"
            )
        
        # Delete associated audit logs
        audit_delete_result = db.db.timesheet_audit.delete_many({
            "user_id": timesheet["user_id"],
            "additional_info.week_data._id": week_id
        })
        
        logger.info(f"Successfully deleted weekly timesheet {week_id} for user {user_name} by manager {current_user.full_name}")
        
        return {
            "message": "Weekly timesheet deleted successfully",
            "week_id": week_id,
            "user_name": user_name,
            "week_start": timesheet.get("week_start"),
            "week_end": timesheet.get("week_end"),
            "deleted_by": current_user.full_name,
            "deleted_at": datetime.now(timezone.utc).isoformat(),
            "audit_logs_deleted": audit_delete_result.deleted_count,
            "image_deleted": bool(image_path and os.path.exists(image_path))
        }
        
    except HTTPException as he:
        logger.error(f"HTTP Exception in delete_weekly_timesheet: {str(he)}")
        raise he
    except Exception as e:
        logger.error(f"Error deleting weekly timesheet: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error deleting weekly timesheet"
        )




@router.patch("/timesheets/{timesheet_id}/update", tags=["timesheets"])
async def edit_timesheet_entry(
    timesheet_id: str,
    update_data: TimesheetUpdate,
    current_user: UserResponse = Depends(verify_manager_role),
    Authorize: AuthJWT = Depends()
):
    """
    Edit a specific timesheet entry for a user. Only managers can edit.
    """
    try:
        Authorize.jwt_required()

        # Find the timesheet document
        timesheet_doc = db.db.timesheet_entries.find_one({"_id": ObjectId(timesheet_id)})
        print(timesheet_doc)

        if not timesheet_doc:
            raise HTTPException(status_code=404, detail="Timesheet not found for the given user and date")

        # Find the index of the day we want to update
        day_index = None
        for i, day in enumerate(timesheet_doc.get('days', [])):
            print(f"->>>>>>> {i}, {day}")
            if day.get('date') == update_data.date:
                day_index = i
                break

        if day_index is None:
            raise HTTPException(status_code=404, detail=f"Day {update_data.date} not found in timesheet")

        # Prepare update fields using the correct array index
        update_fields = {}
        if update_data.time_in is not None:
            update_fields[f"days.{day_index}.time_in"] = update_data.time_in
        if update_data.time_out is not None:
            update_fields[f"days.{day_index}.time_out"] = update_data.time_out
        if update_data.lunch_timeout is not None:
            update_fields[f"days.{day_index}.lunch_timeout"] = update_data.lunch_timeout
        if update_data.total_hours is not None:
            update_fields[f"days.{day_index}.total_hours"] = update_data.total_hours
        
        if not update_fields:
            raise HTTPException(status_code=400, detail="No valid fields to update")

        update_fields["updated_at"] = datetime.now(timezone.utc).isoformat()

        # Update the document using the specific array indices
        result = db.db.timesheet_entries.update_one(
            {"_id": ObjectId(timesheet_id)},
            {"$set": update_fields}
        )
        print("result")

        if result.modified_count == 0:
            raise HTTPException(status_code=404, detail="Timesheet entry not found or not modified")

        return {"message": f"Timesheet {timesheet_id} updated successfully"}

    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error in edit_timesheet_entry: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

