# Flask Mailer with User Management

A Flask-based email campaign management system with user authentication, admin controls, and email tracking capabilities.

## Features

- User authentication system
- Admin dashboard for user management and universal statistics
- User dashboard for individual statistics
- Email campaign creation and tracking
- Modern UI with yellow-based theme using Tailwind CSS
- Responsive design with animations and effects

## Installation

1. Clone the repository
2. Navigate to the Mailer2 directory
3. Install dependencies:
```bash
pip install -r requirements.txt
```

## Initial Setup

1. Initialize the database:
```bash
python db_setup.py
```

This will create:
- Database with required tables
- Default admin account (username: admin, password: admin)

## Running the Application

1. Start the Flask server:
```bash
python app.py
```

2. Open a web browser and navigate to:
```
http://localhost:5000
```

## Default Admin Credentials

- Username: admin
- Password: admin

**Important:** Change these credentials after first login!

## Usage

### Admin Users

1. Login with admin credentials
2. Access admin dashboard
3. Manage users (create/delete)
4. View universal statistics
5. Track all email campaigns

### Regular Users

1. Login with provided credentials
2. Access personal dashboard
3. View individual statistics
4. Create and send email campaigns
5. Track campaign performance

## Security Notes

- All passwords are hashed before storage
- Admin privileges are strictly enforced
- Session-based authentication
- Protected routes for admin functions

## Directory Structure

```
Mailer2/
├── templates/            # HTML templates
├── app.py               # Main application file
├── auth.py             # Authentication module
├── db_setup.py         # Database initialization
├── mailer.py           # Email sending functionality
├── requirements.txt     # Python dependencies
└── README.md           # This file
```

## Technical Stack

- Backend: Flask (Python)
- Database: SQLite
- Frontend: HTML, Tailwind CSS
- Authentication: Flask-Login
- Email: SMTP
