# Timesheet Extraction API

A FastAPI application for extracting and validating timesheet information from images using OpenAI's vision capabilities.

## Features

- Extract timesheet information from images using OpenAI Vision API
- OCR preprocessing using Tesseract
- Validate extracted data against user input
- Handle both single and multiple timesheet records
- Compute and verify working hours
- User role-based access control
- Timesheet management and approval system

## Project Structure

```
├── app/                    # Main application package
│   ├── api/                # API routes and endpoints
│   │   ├── routes/         # Route handlers
│   ├── core/               # Core application components
│   ├── models/             # Database models (if needed)
│   ├── schemas/            # Pydantic models
│   ├── services/           # Business logic services
│   ├── utils/              # Utility functions
│   ├── main.py             # FastAPI application
├── .env                    # Environment variables
├── run.py                 # Entry point script
├── requirements.txt        # Dependencies
└── README.md               # Project documentation
```

## Installation

1. Clone the repository:

```bash
git clone <repository-url>
cd timesheet-api
```

2. Create a virtual environment and activate it:

```bash
python -m venv .venv
# On Windows
.venv\Scripts\activate
# On macOS/Linux
source .venv/bin/activate
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Set up environment variables by creating a `.env` file:

```
OPENAI_API_KEY=your_openai_api_key
MODEL_NAME=gpt-4o
DEBUG=True


JWT Settings
JWT_SECRET_KEY=super-secret-jwt-key-for-development-only

MongoDB Settings 
MONGODB_HOST=localhost
MONGODB_PORT=27017
MONGODB_DB=timesheet_db

# Leave blank if no authentication is required
MONGODB_USERNAME=
MONGODB_PASSWORD=

# SMTP Settings
SMTP_HOST="smtp.gmail.com"
SMTP_PORT=587
SMTP_USER=""
SMTP_PASSWORD=""
SMTP_FROM=""
SMTP_FROM_NAME="Timesheet Extraction Service"

```

## Usage

### Running the Application

Start the application with:

```bash
python run.py
```

This will start the FastAPI application on http://localhost:7779 by default.

### API Endpoints

Available endpoints:
-------------------------------------------------
POST   /api/auth/login        - Login and get access token  
POST   /api/auth/register     - Register a new user
GET    /api/auth/me           - Get current user info
POST   /api/auth/change-password - Change user password
POST   /api/timesheet/upload   - Upload and process a timesheet image

#### Authentication Endpoints
- `POST /api/auth/login` - Login and get access token
- `POST /api/auth/register` - Register a new user
- `GET /api/auth/me` - Get current user profile
- `POST /api/auth/change-password` - Change user password

#### Manager Endpoints
- `GET /api/manager/users` - Get all users (paginated)
- `GET /api/manager/users/{user_id}` - Get specific user's timesheets
- `PUT /api/manager/users/{user_id}/role` - Update user role
- `PUT /api/manager/timesheets/{timesheet_id}/approve` - Approve timesheet entry


#### Upload Timesheet Image

```
POST /api/timesheet/upload
```

Parameters:
- `image_file`: Image file (form data)
- `date`: Date in YYYY-MM-DD format (optional)
- `time_in`: Time in HH:MM format (optional)
- `time_out`: Time out HH:MM format (optional)
- `lunch_timeout`: Lunch timeout in minutes (optional)
- `total_hours`: Total hours worked (optional)
- 'is_daily_entry': Boolean value for daily entry (optional)

Response:
```json
{
  "message": "File uploaded and processed successfully",
  "image_data": {
    "data": {
      "records": [
        {
          "date": "2023-07-01",
          "time_in": "09:00",
          "time_out": "17:00",
          "lunch_timeout": 30,
          "total_hours": 7.5
        }
      ]
    },
    "status": "success"
  },
  "validation_results": {
    "valid": true,
    "message": "All records valid",
    "validation_results": [...]
  }
}
```


## Dependencies

 Download exe file tesrect for OCR
##### https://github.com/UB-Mannheim/tesseract/wiki

- FastAPI - Web framework
- Uvicorn - ASGI server
- Pydantic - Data validation
- OpenAI - AI functionality
- Pytesseract - OCR functionality
- Python-multipart - Form data handling
- fastapi-jwt-auth