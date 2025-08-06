"""
API routes for timesheet operations.
"""

from datetime import datetime, timezone
import os
from traceback import format_exc
from typing import Optional, List

from bson import ObjectId
from fastapi import (
    APIRouter,
    Depends, 
    File, 
    HTTPException, 
    Request,
    status, 
    UploadFile, 
)
from fastapi_jwt_auth import AuthJWT

from backend.core.v1.database import db
from backend.core.v1.logging import logger
from backend.core.v1.security import get_current_user
from backend.services.v1.notification_services import EmailServices
from backend.services.v1.timesheet_services import validate_timesheet_image, validate_timesheet_multiple_images
from backend.schemas.v1.auth import UserResponse
from backend.utils.v1.timesheet import (
    get_week_boundaries_from_input,
    validate_weekday_dates,
    handle_multiple_image_uploads,
    handle_image_upload,
    is_date_within_week_boundary,
    parse_form_data, 
)


router = APIRouter()


@router.post("/draft")
async def save_draft_timesheet(
    request: Request,
    image_files: Optional[UploadFile] = File(None, description="Timesheet image file"),
    current_user: UserResponse = Depends(get_current_user),
    Authorize: AuthJWT = Depends()
):
    try:
        Authorize.jwt_required()
        if not current_user or not hasattr(current_user, "id"):
            raise HTTPException(status_code=401, detail="User not authenticated or invalid user data")

        form = await request.form()
        logger.info(f"form data {form}")

        daily_entries = parse_form_data(form=form)
        logger.info(f"Daily Entry Data is {daily_entries}")

        if image_files:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Please upload all timesheet at the time of the submit."
            )
            
        if not daily_entries:
            raise HTTPException(status_code=400, detail="No daily entries provided")

        entry_dates = [
            datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            for date_str in daily_entries.keys()
        ]
        
        try:
            week_start, week_end = get_week_boundaries_from_input(entry_dates)
            print("##############", week_start, week_end)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        now = datetime.now(timezone.utc)

        daily_document = {
            "user_id": str(current_user.id),
            "week_start": week_start.isoformat(),
            "week_end": week_end.isoformat(),
            "days": list(daily_entries.values()),
            "is_draft": True,
            "is_validated": False,
            "validation_results": {},
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "image_path": None,
            "submitted": False
        }

        existing_doc = db.db.timesheet_entries.find_one({
            "user_id": str(current_user.id),
            "week_start": week_start.isoformat(),
            "week_end": week_end.isoformat()
        })

        if existing_doc:
            if existing_doc['submitted'] == True:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail='Timesheet for this week is already submitted'
                )
            
            existing_entries = {entry["date"]: entry for entry in existing_doc.get("days", [])}
            for date_key, entry in daily_entries.items():
                existing_entries[date_key] = entry
            merged_entries = list(existing_entries.values())
            update_fields = {
                "days": merged_entries,
                "updated_at": now.isoformat(),
                "is_draft": True,
            }
            
            db.db.timesheet_entries.update_one(
                {"_id": existing_doc["_id"]},
                {"$set": update_fields}
            )
            document_id = str(existing_doc["_id"])
        else:
            # if file_path:
            #     daily_document["image_path"] = file_path
            result = db.db.timesheet_entries.insert_one(daily_document)
            document_id = str(result.inserted_id)

        # Retrieve the saved or updated document
        saved_doc = db.db.timesheet_entries.find_one({"_id": ObjectId(document_id)})
        if not saved_doc:
            raise HTTPException(status_code=500, detail="Failed to retrieve saved document")

        logger.info(f"Saved Documennt is {saved_doc}")

        # Send email notification for successful draft save
        email_service = EmailServices()
        await email_service.send_timesheet_submission_confirmation(
            user_id=str(current_user.id),
            timesheet_data=saved_doc["days"],
            # image_path=file_path
        )
        return {
            "message": "Draft timesheet saved successfully",
            "document_id": document_id
        }

    except HTTPException as he:
        logger.error(f"HTTP Exception: {str(he)}")
        raise he
    except Exception as e:
        logger.error(f"Error in save_draft_timesheet: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/validate")
async def validate_timesheet(
    request: Request,
    # Keep backward compatibility - accept both single and multiple files
    image_file: Optional[UploadFile] = File(None, description="Single timesheet image file (legacy)"),
    image_files: Optional[List[UploadFile]] = File(None, description="Multiple timesheet image files (new)"),
    current_user: UserResponse = Depends(get_current_user),
    Authorize: AuthJWT = Depends()
):
    try:
        Authorize.jwt_required()
        if not current_user or not hasattr(current_user, "id"):
            raise HTTPException(status_code=401, detail="User not authenticated or invalid user data")
        
        print("#######################", image_files)
        
        logger.info("Validating the timesheet_data")
        form = await request.form()
        logger.info(f"Validate Form Data {form}")
        daily_entries = parse_form_data(form=form)
        
        # Handle both single and multiple file scenarios
        file_paths = []
        if image_files:
            file_paths = await handle_multiple_image_uploads(image_files=image_files)
        
    
        # New submission or update
        entry_dates = []
        for date_str in daily_entries.keys():
            try:
                dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                entry_dates.append(dt)
            except ValueError as e:
                logger.error(f"Invalid date format for {date_str}: {str(e)}")
                raise HTTPException(status_code=400, detail=f"Invalid date format: {date_str}")
        if not entry_dates:
            raise HTTPException(status_code=400, detail="No valid daily entries provided")
        
        # Validate that no entries are on weekends
        # validate_weekday_dates(entry_dates)

        week_start, week_end = get_week_boundaries_from_input(entry_dates)
        existing_doc = db.db.timesheet_entries.find_one({
            "user_id": str(current_user.id),
            "week_start": week_start.isoformat(),
            "week_end": week_end.isoformat()
        })
        
        if existing_doc['submitted'] == True:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Timesheet for this week is already submitted."
            )

        # Handle file paths - prefer new uploads, fall back to existing
        final_file_paths = file_paths
        
        if not final_file_paths:
            if existing_doc and "image_path" in existing_doc and existing_doc["image_path"]:
                final_file_paths = [existing_doc["image_path"]]
                logger.info(f"Using existing single image: {final_file_paths}")
            
            if not final_file_paths:
                raise HTTPException(status_code=400, detail="No images available for validation and none provided")

        now = datetime.now(timezone.utc)
        
        # CRITICAL: Keep using image_path field for compatibility
        primary_image_path = None
        
        if existing_doc:
            # Append the new files with old ones.
            if file_paths and existing_doc.get("image_path"):
                final_file_paths = existing_doc['image_path'] + final_file_paths
                # try:
                #     if existing_doc["image_path"] not in final_file_paths:
                #         os.remove(existing_doc["image_path"])
                #         logger.info(f"Removed old image at: {existing_doc['image_path']}")
                # except Exception as e:
                #     logger.error(f"Failed to remove old image: {str(e)}")

            existing_entries = {entry["date"]: entry for entry in existing_doc.get("days", [])}
            for date_key, entry in daily_entries.items():
                existing_entries[date_key] = entry
            merged_entries = list(existing_entries.values())
            
            update_fields = {
                "days": merged_entries,
                "updated_at": now.isoformat(),
                "is_draft": False,
                "is_validated": False,  # Initial state before validation
                "validation_results": {},
                "image_path": final_file_paths,  # KEEP this field for compatibility,,  # KEEP this field
                "submitted": True
                # "image_path": final_file_paths
            }
            
            db.db.timesheet_entries.update_one(
                {"_id": existing_doc["_id"]},
                {"$set": update_fields}
            )
            document_id = str(existing_doc["_id"])
        else:
            # New document - KEEP using image_path field
            daily_document = {
                "user_id": str(current_user.id),
                "week_start": week_start.isoformat(),
                "week_end": week_end.isoformat(),
                "days": list(daily_entries.values()),
                "is_draft": False,
                "is_validated": False,
                "validation_results": {},
                "created_at": now.isoformat(),
                "updated_at": now.isoformat(),
                "image_path": final_file_paths,  # KEEP this field
                "submitted": True
            }
            result = db.db.timesheet_entries.insert_one(daily_document)
            document_id = str(result.inserted_id)

        # Retrieve the saved week_data
        week_data = db.db.timesheet_entries.find_one({"_id": ObjectId(document_id)})
        if not week_data:
            raise HTTPException(status_code=500, detail="Failed to retrieve saved document")
        week_data["_id"] = str(week_data["_id"])

        # Send submission confirmation email - KEEP using single image_path
        email_service = EmailServices()
        await email_service.send_timesheet_submission_confirmation(
            user_id=str(current_user.id),
            timesheet_data=week_data["days"],
            # image_path=final_file_paths  # Email service unchanged
        )

        # Multiple images - use new function
        validation_result = await validate_timesheet_multiple_images(
            image_paths=final_file_paths,
            current_user=current_user,
            week_data=week_data
        )
    
        # Update with validation results
        update_fields = {
            "is_validated": True,
            "validation_results": validation_result["validation_results"],
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        db.db.timesheet_entries.update_one(
            {"_id": ObjectId(document_id)},
            {"$set": update_fields}
        )

        return {
            "message": "Final timesheet submitted and validated successfully",
            "document_id": document_id,
            "validation_result": validation_result,
            "files_processed": len(final_file_paths)
        }
    except HTTPException as he:
        logger.error(f"HTTP Exception: {str(he)}")
        raise he
    except Exception as e:
        print(format_exc())
        logger.error(f"Error in validate_timesheet: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
    
    
def get_dates_from_timesheets(user_id: str):
    """
    Fetches dates from timesheet entries that belong to the logged-in user.
    """
    try:
        query = {
            "user_id": user_id,  # Filter by logged-in user
            "$or": [{"is_draft": True}, {"is_draft": False}]
        }
        timesheets = db.timesheet_entries.find(query, {"days.date": 1, "_id": 0})
        
        dates = []
        for entry in timesheets:
            for day in entry.get("days", []):
                dates.append(day["date"])
        
        return dates
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/timesheets/dates", response_model=list[str], tags=["timesheets"])
async def get_timesheet_dates(
    current_user: dict = Depends(get_current_user), 
    Authorize: AuthJWT = Depends()
):
    """
    Fetch all dates from timesheet entries belonging to the logged-in user.
    """
    Authorize.jwt_required()  # Ensure authentication
    if not current_user or not hasattr(current_user, "id"):
        raise HTTPException(status_code=401, detail="User not authenticated or invalid user data")

    user_id = str(current_user.id)  # Get user ID from authentication
    return get_dates_from_timesheets(user_id)


def get_dates_from_timesheets_draft(user_id: str):
    """
    Fetches dates from timesheet entries where is_draft is True and is_submit is False.
    """
    try:
        query = {
            "user_id": user_id,
            "is_draft": True,
            "is_validated": False
        }
        timesheets = db.timesheet_entries.find(query, {"days": 1, "_id": 0})
        
        entries = []
        for entry in timesheets:
            for day in entry.get("days", []):
                entries.append({
                    "date": str(day["date"]),
                    "time_in": str(day["time_in"]),
                    "time_out": str(day["time_out"]),
                    "lunch_timeout": str(day["lunch_timeout"]),
                    "total_hours": str(day["total_hours"])
                })
                        
        return entries
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/timesheets/dates/draft", response_model=list[dict], tags=["timesheets"])
async def get_timesheet_dates_draft(
    current_user: dict = Depends(get_current_user),
    Authorize: AuthJWT = Depends()
):
    """
    Fetch all dates from timesheet entries where is_draft is True and is_submit is False.
    """
    Authorize.jwt_required()  # Ensure authentication
    if not current_user or not hasattr(current_user, "id"):
        raise HTTPException(status_code=401, detail="User not authenticated or invalid user data")

    user_id = str(current_user.id)  # Get user ID from authentication
    return get_dates_from_timesheets_draft(user_id)



@router.delete("/timesheet/date/{date}", tags=["timesheets"])
async def delete_draft_timesheet_by_date(
    date: str,
    current_user: UserResponse = Depends(get_current_user),
    Authorize: AuthJWT = Depends()
):
    """
    Delete a draft timesheet entry for a specific date. Only draft entries can be deleted.
    """
    try:
        Authorize.jwt_required()
        if not current_user or not hasattr(current_user, "id"):
            raise HTTPException(status_code=401, detail="User not authenticated or invalid user data")

        # Validate date format
        try:
            datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

        # Find and update timesheet entries to remove the specific date
        result = db.db.timesheet_entries.update_many(
            {
                "user_id": str(current_user.id),
                "days.date": date,
                "is_draft": True,
                "is_validated": False
            },
            {
                "$pull": {"days": {"date": date}},
                "$set": {"updated_at": datetime.now(timezone.utc).isoformat()}
            }
        )

        if result.modified_count == 0:
            raise HTTPException(
                status_code=404, 
                detail=f"No draft timesheet entry found for date {date}"
            )

        return {
            "message": f"Successfully deleted draft timesheet entry for date {date}",
            "date": date
        }

    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error in delete_draft_timesheet_by_date: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

