from typing import List, Dict, Any, Optional
from app.core.config import settings
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr
from datetime import timezone, timedelta
from email.message import EmailMessage
from email.utils import formataddr
import datetime
from smtplib import SMTP
from app.core.logging import logger
from app.core.database import db
import os
from email.mime.image import MIMEImage
from bson import ObjectId

class EmailServices:
    
    def __init__(self):
        self.smtp_host = settings.SMTP_HOST
        self.smtp_port = settings.SMTP_PORT
        self.smtp_user = settings.SMTP_USER
        self.smtp_password = settings.SMTP_PASSWORD
        self.smtp_from = settings.SMTP_FROM
        self.smtp_from_name = settings.SMTP_FROM_NAME
        
    def create_smtp_connection(self):
        """ Create a connection to the SMTP server"""
        
        try:
            smtp_server = SMTP(self.smtp_host, self.smtp_port)
            smtp_server.starttls()
            smtp_server.login(self.smtp_user, self.smtp_password)
            logger.info("SMTP connection created successfully")
            return smtp_server
        except Exception as e:
            logger.error(f"Error creating SMTP connection: {e}")
            raise e
        
    def create_email_message(
        self,
        to_email: List[str],
        subject: str,
        body: str,
    ):
        """ Create an email message with a html content"""
        
        message = MIMEMultipart()   
        message["From"] = formataddr((self.smtp_from_name, self.smtp_from))
        message["To"] = ", ".join(to_email)
        message["Subject"] = subject
        message.attach(MIMEText(body, "html"))
        return message
    
    async def get_user_email(self, user_id: str) -> Optional[str]:
        """ Get the email of a user from the database"""
        
        try:
            user = db.db.users.find_one({"_id": ObjectId(user_id)})
            return user.get("email") if user else None
        except Exception as e:
            logger.error(f"Error getting user email: {e}")
            return None
        
    def format_timesheet_table(self, timesheet_records: List[Dict[str, Any]]) -> str:
        """ Format a list of timesheet records into an html table"""
        
        if not timesheet_records:
            return "No timesheet records found"
        
        table_rows = ""
        running_total_minutes = 0  # Initialize running total

        # Helper function to parse "HH:MM" to total minutes
        def parse_to_minutes(time_str: str) -> int:
            try:
                hours, minutes = map(int, time_str.split(':'))
                return hours * 60 + minutes
            except (ValueError, AttributeError):
                return 0
            
        # Helper function to convert total minutes to "HH:MM"
        def minutes_to_hhmm(minutes: int) -> str:
            hours = minutes // 60
            mins = minutes % 60
            return f"{hours:02d}:{mins:02d}"
        
        for record in timesheet_records:
            date = record.get("date", "N/A")
            time_in = record.get("time_in", "N/A")
            time_out = record.get("time_out", "N/A")
            lunch_timeout = record.get("lunch_timeout", "N/A")
            # record_hours = float(record.get("total_hours", 0))  # Get hours for this record
            # running_total += record_hours  # Add to running total

            # Use total_hours as a string for display
            total_hours_display = record.get("total_hours", "0:00")
            if not isinstance(total_hours_display, str):
                total_hours_display = str(total_hours_display)
            
            # Parse to minutes for running total
            record_minutes = parse_to_minutes(total_hours_display)
            running_total_minutes += record_minutes
            
            table_rows += f"""
            <tr>
                <td style="padding: 10px; border: 1px solid #ddd;">{date}</td>
                <td style="padding: 10px; border: 1px solid #ddd;">{time_in}</td>
                <td style="padding: 10px; border: 1px solid #ddd;">{time_out}</td>
                <td style="padding: 10px; border: 1px solid #ddd;">{lunch_timeout}</td>
                <td style="padding: 10px; border: 1px solid #ddd;">{total_hours_display}</td>
            </tr>
            """
        # Calculate total in HH:MM
        total_hhmm = minutes_to_hhmm(running_total_minutes)
        
        return f"""
        <table style="width: 100%; border-collapse: collapse; margin-top: 20px;">
            <thead>
                <tr style="background-color: #f2f2f2;">
                    <th style="padding: 8px; border: 1px solid #ddd;">Date</th>
                    <th style="padding: 8px; border: 1px solid #ddd;">Time In</th>
                    <th style="padding: 8px; border: 1px solid #ddd;">Time Out</th>
                    <th style="padding: 8px; border: 1px solid #ddd;">Lunch Break</th>
                    <th style="padding: 8px; border: 1px solid #ddd;">Hours</th>
                </tr>
            </thead>
            <tbody>
                {table_rows}
            </tbody>
            <tfoot>
                <tr style="background-color: #f2f2f2;">
                    <td colspan="4" style="padding: 8px; border: 1px solid #ddd; text-align: right;">
                        <strong>Total Hours:</strong>
                    </td>
                    <td style="padding: 8px; border: 1px solid #ddd;">
                        <strong>{total_hhmm}</strong>
                    </td>
                </tr>
            </tfoot>
        </table>
        """

    async def send_daily_entry_confirmation(
        self,
        user_id: str,
        entry_date: str,
        entry_details
    ):
        """ Send a daily entry confirmation email to the user"""
        
        try:
            user_email = await self.get_user_email(user_id)
            if not user_email:
                logger.error(f"User with id {user_id} not found")
                return False
             # Format the single entry as a list for the table
            single_record = [{
                "date": entry_date,
                "time_in": entry_details['time_in'].strftime("%H:%M") if hasattr(entry_details['time_in'], 'strftime') else entry_details['time_in'],
                "time_out": entry_details['time_out'].strftime("%H:%M") if hasattr(entry_details['time_out'], 'strftime') else entry_details['time_out'],
                "lunch_timeout": entry_details['lunch_timeout'],
                "total_hours": entry_details['total_hours']
            }]
            
            # Use the format_timesheet_table method
            table_html = self.format_timesheet_table(single_record)
            
            
            html_content = f"""
            <html>
            <head>
                <style>
                    body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                    .container {{ padding: 20px; }}
                    .header {{ background-color: #f8f9fa; padding: 20px; margin-bottom: 20px; }}
                    .details {{ background-color: #fff; padding: 15px; border: 1px solid #ddd; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h2>Daily Timesheet Entry Confirmation</h2>
                        <p>Your timesheet entry for {entry_date} has been recorded.</p>
                    </div>
                    
                    <div class="details">
                        <h3>Entry Details:</h3>
                        {table_html}
                    </div>
                </div>
            </body>
            </html>
            """
            
            smtp_server = self.create_smtp_connection()
            try:
                message = self.create_email_message(
                    to_email=[user_email],
                    subject="Daily Timesheet Entry Confirmation",
                    body=html_content
                )
                smtp_server.sendmail(self.smtp_from, [user_email], message.as_string())
                logger.info(f"Daily entry confirmation email sent to {user_email}")
                return True
            finally:
                smtp_server.quit()
            
        except Exception as e:
            logger.error(f"Error sending daily entry confirmation email: {e}")
            return False

    async def send_timesheet_validation_results(
        self,
        user_id: str,
        comparison_results: Dict[str, Any],
        extracted_data: Dict[str, Any],  # New parameter
        is_submission: bool
    ):
        try:
            user_email = await self.get_user_email(user_id)
            if not user_email:
                logger.error(f"User with id {user_id} not found")
                return False

            # Format extracted data from image with error handling
            extracted_records = []
            for record in extracted_data.get('records', []):
                try:
                    extracted_records.append({
                        "date": record.get("date", "N/A"),
                        "time_in": record.get("time_in", "N/A"),
                        "time_out": record.get("time_out", "N/A"),
                        "lunch_timeout": str(record.get("lunch_timeout", "N/A")),
                        "total_hours": float(record.get("total_hours", 0))
                    })
                except (ValueError, TypeError) as e:
                    logger.error(f"Error formatting record: {e}")
                    continue

            # Format extracted data from image
            extracted_records = [
                {
                    "date": record["date"],
                    "time_in": record["time_in"],
                    "time_out": record["time_out"],
                    "lunch_timeout": record["lunch_timeout"],
                    "total_hours": record["total_hours"]
                }
                for record in comparison_results.get("extracted_data", {}).get("records", [])
            ]
            extracted_table = self.format_timesheet_table(extracted_records) if extracted_records else "<p>No data extracted from image</p>"

            # Format matching entries
            matching_records = [
                {
                    "date": match["date"],
                    "time_in": match["data"]["time_in"],
                    "time_out": match["data"]["time_out"],
                    "lunch_timeout": match["data"]["lunch_timeout"],
                    "total_hours": match["data"]["total_hours"]
                }
                for match in comparison_results.get("matches", [])
            ]
            matches_table = self.format_timesheet_table(matching_records) if matching_records else "<p>No matching entries found</p>"

            # Format mismatched entries
            mismatched_records = [
                {
                    "date": mismatch["date"],
                    "time_in": mismatch["timesheet_data"]["time_in"],
                    "time_out": mismatch["timesheet_data"]["time_out"],
                    "lunch_timeout": mismatch["timesheet_data"]["lunch_timeout"],
                    "total_hours": mismatch["timesheet_data"]["total_hours"]
                }
                for mismatch in comparison_results.get("mismatches", [])
            ]
            mismatches_table = self.format_timesheet_table(mismatched_records) if mismatched_records else "<p>No mismatched entries found</p>"

            # Format missing entries
            missing_records = [
                {
                    "date": record["data"]["date"],
                    "time_in": record["data"]["time_in"],
                    "time_out": record["data"]["time_out"],
                    "lunch_timeout": record["data"]["lunch_timeout"],
                    "total_hours": record["data"]["total_hours"]
                }
                for record in comparison_results.get("missing_entries", [])
            ]
            missing_table = self.format_timesheet_table(missing_records) if missing_records else "<p>No missing entries found</p>"

            html_content = f"""
            <html>
            <head>
                <style>
                    body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                    .container {{ padding: 20px; }}
                    .header {{ background-color: #f8f9fa; padding: 20px; margin-bottom: 20px; }}
                    .details {{ background-color: #fff; padding: 15px; border: 1px solid #ddd; margin-bottom: 20px; }}
                    .section-title {{ color: #2c3e50; margin-top: 20px; }}
                    .validation-status {{ 
                        padding: 10px; 
                        margin-bottom: 15px; 
                        border-radius: 4px;
                        background-color: {comparison_results.get('valid', False) and '#d4edda' or '#f8d7da'};
                        color: {comparison_results.get('valid', False) and '#155724' or '#721c24'};
                    }}
                    .summary {{ background-color: #e9ecef; padding: 10px; margin: 10px 0; border-radius: 4px; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h2>Timesheet Validation Results</h2>
                        <div class="validation-status">
                            <strong>Status:</strong> {comparison_results.get('message', 'Validation completed')}
                        </div>
                    </div>

                    <div class="details">
                        <h3 class="section-title">Validation Summary</h3>
                        <div class="summary">
                            <p>✓ Matching Entries: {len(matching_records)}</p>
                            <p>⚠ Mismatched Entries: {len(mismatched_records)}</p>
                            <p>❌ Missing Entries: {len(missing_records)}</p>
                        </div>
                    </div>
                    
                    <div class="details">
                        <h3 class="section-title">Matching Entries</h3>
                        <p>These entries match with the system records:</p>
                        {matches_table}
                    </div>

                    <div class="details">
                        <h3 class="section-title">Mismatched Entries</h3>
                        <p>These entries have discrepancies with system records:</p>
                        {mismatches_table}
                    </div>
                    
                    <div class="details">
                        <h3 class="section-title">Missing Entries</h3>
                        <p>These entries need to be submitted to the system:</p>
                        {missing_table}
                    </div>
                    
                    <div class="details">
                        <h3>Next Steps</h3>
                        <ul>
                            <li>Review the extracted data for accuracy</li>
                            <li>Submit any missing entries through the daily entry form</li>
                            <li>Check and update any mismatched entries</li>
                            <li>Contact your supervisor if you need assistance</li>
                        </ul>
                    </div>
                </div>
            </body>
            </html>
            """
            
            smtp_server = self.create_smtp_connection()
            try:
                message = self.create_email_message(
                    to_email=[user_email],
                    subject="Timesheet Validation Results",
                    body=html_content
                )
                smtp_server.sendmail(self.smtp_from, [user_email], message.as_string())
                logger.info(f"Validation results email sent to {user_email}")
                return True
            finally:
                smtp_server.quit()
                
        except Exception as e:
            logger.error(f"Error sending validation results email: {e}")
            return False

    def format_mismatches_detail(self, mismatches: List[Dict[str, Any]]) -> str:
        if not mismatches:
            return ""
            
        details = ""
        for mismatch in mismatches:
            details += f"""
            <div class="mismatch-detail" style="margin-top: 15px; padding: 10px; border: 1px solid #ffc107; border-radius: 4px;">
                <h4>Date: {mismatch['date']}</h4>
                <div class="comparison">
                    <div>
                        <h5>Stored Values:</h5>
                        <ul>
                            {"".join([
                                f"<li>{m['field']}: {m['stored_value']}</li>"
                                for m in mismatch.get('mismatches', [])
                            ])}
                        </ul>
                    </div>
                    <div>
                        <h5>Timesheet Values:</h5>
                        <ul>
                            {"".join([
                                f"<li>{m['field']}: {m['timesheet_value']}</li>"
                                for m in mismatch.get('mismatches', [])
                            ])}
                        </ul>
                    </div>
                </div>
            </div>
            """
        return details

    def format_missing_entries(self, missing_entries: List[Dict[str, Any]]) -> str:
        if not missing_entries:
            return "<li>No missing entries found</li>"
             
        return "".join([
            f"<li>{entry['date']} - No stored entry found</li>"
            for entry in missing_entries
        ])


    async def send_timesheet_approval_notification(
        self,
        user_id: str,
        timesheet_id: str,
        approved_by: str,
        timesheet_data: Dict[str, Any]
    ):
        """Send notification when timesheet is approved"""
        try:
            user_email = await self.get_user_email(user_id)
            if not user_email:
                logger.error(f"User with id {user_id} not found")
                return False

            # Format timesheet data for display
            timesheet_records = [{
                "date": timesheet_data["date"].strftime("%Y-%m-%d") if hasattr(timesheet_data["date"], 'strftime') else timesheet_data["date"],
                "time_in": timesheet_data["time_in"].strftime("%H:%M") if hasattr(timesheet_data["time_in"], 'strftime') else timesheet_data["time_in"],
                "time_out": timesheet_data["time_out"].strftime("%H:%M") if hasattr(timesheet_data["time_out"], 'strftime') else timesheet_data["time_out"],
                "lunch_timeout": timesheet_data["lunch_timeout"],
                "total_hours": timesheet_data["total_hours"]
            }]
            
            
            table_html = self.format_timesheet_table(timesheet_records)

            html_content = f"""
            <html>
            <head>
                <style>
                    body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                    .container {{ padding: 20px; }}
                    .header {{ background-color: #f8f9fa; padding: 20px; margin-bottom: 20px; }}
                    .details {{ background-color: #fff; padding: 15px; border: 1px solid #ddd; }}
                    .success {{ color: #28a745; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h2>Timesheet Approval Notification</h2>
                        <p class="success">Your timesheet has been approved!</p>
                    </div>
                    
                    <div class="details">
                        <p><strong>Timesheet ID:</strong> {timesheet_id}</p>
                        <p><strong>Approved By:</strong> {approved_by}</p>
                        <p><strong>Approval Date:</strong> {datetime.datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")} UTC</p>
                        
                        <h3>Approved Timesheet Details:</h3>
                        {table_html}
                    </div>
                </div>
            </body>
            </html>
            """

            smtp_server = self.create_smtp_connection()
            try:
                message = self.create_email_message(
                    to_email=[user_email],
                    subject="Timesheet Approved",
                    body=html_content
                )
                smtp_server.sendmail(self.smtp_from, [user_email], message.as_string())
                logger.info(f"Approval notification sent to {user_email}")
                return True
            finally:
                smtp_server.quit()

        except Exception as e:
            logger.error(f"Error sending approval notification: {e}")
            return False

    async def send_timesheet_submission_confirmation(
        self,
        user_id: str,
        timesheet_data: List[Dict[str, Any]],
        image_path: Optional[str] = None  # New parameter for image path
    ):
        """Send a confirmation email when a timesheet is successfully submitted, including image if provided"""
        try:
            user_email = await self.get_user_email(user_id)
            if not user_email:
                logger.error(f"User with id {user_id} not found")
                return False

            # Format the timesheet data into an HTML table
            table_html = self.format_timesheet_table(timesheet_data)

            # Create the email content
            html_content = f"""
            <html>
            <head>
                <style>
                    body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                    .container {{ padding: 20px; }}
                    .header {{ background-color: #f8f9fa; padding: 20px; margin-bottom: 20px; }}
                    .details {{ background-color: #fff; padding: 15px; border: 1px solid #ddd; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h2>Timesheet Submission Confirmation</h2>
                        <p>Your timesheet has been successfully submitted.</p>
                    </div>
                    
                    <div class="details">
                        <h3>Submitted Timesheet Details:</h3>
                        {table_html}
                    </div>
                </div>
            </body>
            </html>
            """

            # Create a multipart message to support both HTML content and image attachment
            message = MIMEMultipart()
            message["From"] = self.smtp_from
            message["To"] = user_email
            message["Subject"] = "Timesheet Submitted Successfully"

            # Attach the HTML content
            message.attach(MIMEText(html_content, "html"))

            # Attach the image if provided
            if image_path and os.path.exists(image_path):
                try:
                    with open(image_path, "rb") as img_file:
                        img_data = img_file.read()
                    image = MIMEImage(img_data, name=os.path.basename(image_path))
                    message.attach(image)
                    logger.info(f"Image attached to email from path: {image_path}")
                except Exception as e:
                    logger.error(f"Error attaching image: {str(e)}")
            else:
                logger.info("No image provided or image path does not exist; sending email without attachment")

            # Create SMTP connection
            smtp_server = self.create_smtp_connection()
            try:
                # Send the email
                smtp_server.sendmail(self.smtp_from, [user_email], message.as_string())
                logger.info(f"Submission confirmation email sent to {user_email}")
                return True
            finally:
                smtp_server.quit()

        except Exception as e:
            logger.error(f"Error sending submission confirmation email: {str(e)}")
            return False



