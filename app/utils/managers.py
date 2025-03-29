from app.core.logging import logger

def merge_audit_info_into_week(week_data: dict, formatted_audit_logs: list) -> dict:
    """
    Merge day-level validation info from the audit log's stored week_data into week_data.
    Only the simple string from "validation_info_status" is retained.
    """
    audit_week_data = {}
    if formatted_audit_logs:
        audit_week = formatted_audit_logs[0].get("additional_info", {}).get("week_data", {})
        for day in audit_week.get("days", []):
            key = day.get("date", "")[:10]
            stored_val_status = (
                day.get("validation_info", {}).get("status", "unknown")
                if isinstance(day.get("validation_info"), dict)
                else day.get("validation_info", "unknown")
            )
            audit_week_data[key] = {
                "status": day.get("status", "unknown"),
                "validation_info_status": stored_val_status
            }
    
    for day in week_data.get("days", []):
        day_key = day.get("date", "")[:10]
        if day_key in audit_week_data:
            day["status"] = audit_week_data[day_key].get("status", day.get("status"))
            day["validation_info_status"] = audit_week_data[day_key].get("validation_info_status", "unknown")
        else:
            day["validation_info_status"] = "unknown"
        # Remove any extra validation_info field.
        day.pop("validation_info", None)


    logger.info(f"Merge day-level validation info from the audit log's stored week_data into week_data.")
    logger.info(f"Audit Log week Data : {week_data}")
    return week_data