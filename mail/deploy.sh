#!/bin/bash

# Deployment Script for Pixel Tracker

# Exit on any error
set -e

# Check if required files exist
REQUIRED_FILES=("pixel_tracker_py2.py" "requirements.txt" "mailer.py")
for file in "${REQUIRED_FILES[@]}"; do
    if [ ! -f "$file" ]; then
        echo "Error: $file is missing"
        exit 1
    fi
done

# Create virtual environment if not exists
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Upgrade pip
pip install --upgrade pip

# Install dependencies
pip install -r requirements.txt

# Ensure tracking data directory exists
mkdir -p tracking_logs

# Start pixel tracker in background
nohup gunicorn -w 4 -b 0.0.0.0:8080 pixel_tracker_py2:app &

# Optional: Start dashboard in background
nohup streamlit run dashboard.py --server.port 8501 &

echo "Deployment completed successfully!"
