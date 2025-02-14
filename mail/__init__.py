# Tracker package initialization
# This file helps Python treat the directory as a package

import os
import logging
from logging.handlers import RotatingFileHandler

# Configure logging
def setup_logging():
    # Create logs directory if it doesn't exist
    if not os.path.exists('logs'):
        os.makedirs('logs')
        
    # Configure file handler
    file_handler = RotatingFileHandler(
        'logs/flask_mailer.log',
        maxBytes=1024 * 1024,  # 1MB
        backupCount=10
    )
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
    ))
    file_handler.setLevel(logging.INFO)
    
    # Configure console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    ))
    console_handler.setLevel(logging.INFO)
    
    # Get the root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    # Remove any existing handlers
    root_logger.handlers = []
    
    # Add handlers
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

# Set up logging when the module is imported
setup_logging()
