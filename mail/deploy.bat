@echo off
setlocal enabledelayedexpansion

REM Check if required files exist
set REQUIRED_FILES[0]=pixel_tracker_py2.py
set REQUIRED_FILES[1]=requirements.txt
set REQUIRED_FILES[2]=mailer.py

for /L %%i in (0,1,2) do (
    if not exist !REQUIRED_FILES[%%i]! (
        echo Error: !REQUIRED_FILES[%%i]! is missing
        exit /b 1
    )
)

REM Create virtual environment if not exists
if not exist venv (
    python -m venv venv
)

REM Activate virtual environment
call venv\Scripts\activate

REM Upgrade pip
pip install --upgrade pip

REM Install dependencies
pip install -r requirements.txt

REM Start pixel tracker in background
start /B gunicorn -w 4 -b 0.0.0.0:8080 pixel_tracker_py2:app

REM Optional: Start dashboard in background
start /B streamlit run dashboard.py --server.port 8501

echo Deployment completed successfully!
