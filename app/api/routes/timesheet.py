"""
API routes for timesheet operations.
"""

import os
from datetime import datetime, timezone
from app.services.timesheet_services import validate_timesheet_image
from app.core.database import db
from fastapi import APIRouter, File, HTTPException, UploadFile, Depends, Request
from typing import Optional
from bson import ObjectId

from datetime import datetime
from app.core.logging import logger
from app.services.notification_services import EmailServices
from app.core.security import get_current_user
from app.schemas.auth import UserResponse
from app.utils.timesheet import get_week_boundaries_from_input, validate_weekday_dates
from fastapi_jwt_auth import AuthJWT
from app.utils.timesheet import parse_form_data, handle_image_upload


router = APIRouter()


@router.post("/draft")
async def save_draft_timesheet(
    request: Request,
    image_file: Optional[UploadFile] = File(None, description="Timesheet image file"),
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

        if not daily_entries:
            raise HTTPException(status_code=400, detail="No daily entries provided")

        entry_dates = [datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                       for date_str in daily_entries.keys()]
        

        # Validate that no entries are on weekends
        # validate_weekday_dates(entry_dates)

        # week_start, week_end = get_week_boundaries_from_input(entry_dates)
        try:
            week_start, week_end = get_week_boundaries_from_input(entry_dates)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        file_path = await handle_image_upload(image_file)

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
                "image_path": file_path
            }

        existing_doc = db.db.timesheet_entries.find_one({
            "user_id": str(current_user.id),
            "week_start": week_start.isoformat(),
            "week_end": week_end.isoformat()
        })

        if existing_doc:
            existing_entries = {entry["date"]: entry for entry in existing_doc.get("days", [])}
            for date_key, entry in daily_entries.items():
                existing_entries[date_key] = entry
            merged_entries = list(existing_entries.values())
            update_fields = {
                "days": merged_entries,
                "updated_at": now.isoformat(),
                "is_draft": True,
            }
            if file_path:
                update_fields["image_path"] = file_path
            else:
                # Preserve existing image_path if no new image provided
                if "image_path" in existing_doc:
                    update_fields["image_path"] = existing_doc["image_path"]
            db.db.timesheet_entries.update_one(
                {"_id": existing_doc["_id"]},
                {"$set": update_fields}
            )
            document_id = str(existing_doc["_id"])
        else:
            if file_path:
                daily_document["image_path"] = file_path
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
            image_path=file_path
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
    image_file: Optional[UploadFile] = File(None, description="Timesheet image file"),
    current_user: UserResponse = Depends(get_current_user),
    Authorize: AuthJWT = Depends()
):
    try:
        Authorize.jwt_required()
        if not current_user or not hasattr(current_user, "id"):
            raise HTTPException(status_code=401, detail="User not authenticated or invalid user data")
        logger.info("Validating the timesheet_data")
        form = await request.form()
        logger.info(f"Validate Form Data {form}")
        daily_entries = parse_form_data(form=form)
        file_path = await handle_image_upload(image_file=image_file)

        if daily_entries:
            # New submission or update
            entry_dates = []
            for date_str in daily_entries.keys():
                try:
                    print("aaaaaaaaaaaaaaaaaa")
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
            print("bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb")

            if not file_path:
                if existing_doc and "image_path" in existing_doc and existing_doc["image_path"]:
                    # Use existing image if no new one provided and updating
                    file_path = existing_doc["image_path"]
                    logger.info(f"Using existing image at: {file_path}")
                else:
                    raise HTTPException(status_code=400, detail="No image available for validation and none provided")

            now = datetime.now(timezone.utc)
            if existing_doc:
                # Update existing document
                if image_file and existing_doc.get("image_path") and existing_doc["image_path"] != file_path:
                    try:
                        os.remove(existing_doc["image_path"])
                        logger.info(f"Removed old image at: {existing_doc['image_path']}")
                    except Exception as e:
                        logger.error(f"Failed to remove old image: {str(e)}")

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
                    "image_path": file_path
                }
                db.db.timesheet_entries.update_one(
                    {"_id": existing_doc["_id"]},
                    {"$set": update_fields}
                )
                document_id = str(existing_doc["_id"])
            else:
                # New document
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
                    "image_path": file_path
                }
                result = db.db.timesheet_entries.insert_one(daily_document)
                document_id = str(result.inserted_id)

            # Retrieve the saved week_data
            week_data = db.db.timesheet_entries.find_one({"_id": ObjectId(document_id)})
            if not week_data:
                raise HTTPException(status_code=500, detail="Failed to retrieve saved document")
            week_data["_id"] = str(week_data["_id"])

            # Send submission confirmation email
            email_service = EmailServices()
            await email_service.send_timesheet_submission_confirmation(
                user_id=str(current_user.id),
                timesheet_data=week_data["days"]
            )
            print(file_path, "llllllllllllllllllllllllllllllllll")

            # Perform validation
            validation_result = await validate_timesheet_image(
                image_path=file_path,
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
                "validation_result": validation_result
            }
        else:
            # Validate existing most recent final entry

            most_recent_final_entry = db.db.timesheet_entries.find_one(
                {"user_id": str(current_user.id), "is_draft": True},
                sort=[("week_start", -1)]
            )
            if not most_recent_final_entry:
                raise HTTPException(status_code=404, detail="No final timesheet found to validate")
            # if "image_path" not in most_recent_final_entry or not most_recent_final_entry["image_path"]:
            #     raise HTTPException(status_code=400, detail="No image available for validation")

            most_recent_final_entry["_id"] = str(most_recent_final_entry["_id"])

            # Perform validation
            validation_result = await validate_timesheet_image(
                image_path=file_path,
                current_user=current_user,
                week_data=most_recent_final_entry
            )

            # Update validation results in database
            update_fields = {
                "is_validated": True,
                "validation_results": validation_result["validation_results"],
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
            db.db.timesheet_entries.update_one(
                {"_id": ObjectId(most_recent_final_entry["_id"])},
                {"$set": update_fields}
            )

            return {
                "message": "Validation performed on the most recent final timesheet",
                "validation_result": validation_result
            }

    except HTTPException as he:
        logger.error(f"HTTP Exception: {str(he)}")
        raise he
    except Exception as e:
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

