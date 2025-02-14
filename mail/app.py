from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, abort, send_file
import os
from functools import wraps
from datetime import datetime
import uuid
from werkzeug.utils import secure_filename
import mimetypes
import base64
import io
import re
import logging
from logging.handlers import RotatingFileHandler
import os.path

from auth import authenticate_user, create_user, delete_user, get_user_stats, get_admin_stats
from mailer import EmailSender, parse_recipients, get_campaign_id
from dashboard import dashboard
from pixel_tracker_py2 import track_pixel, Base, PixelTrack
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

# Constants and path configurations
import os.path

# Get the absolute path of the application directory
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
LOGS_DIR = os.path.join(BASE_DIR, 'logs')
DB_PATH = os.path.join(BASE_DIR, 'tracking.db')

# Create required directories
for directory in [UPLOAD_FOLDER, LOGS_DIR]:
    if not os.path.exists(directory):
        os.makedirs(directory)

# Configure logging for Windows
def setup_logging():
    try:
        # Configure file handler with rotation
        log_file = os.path.join(LOGS_DIR, 'flask_mailer.log')
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=1024 * 1024,  # 1MB
            backupCount=10,
            encoding='utf-8'  # Explicitly set encoding for Windows
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

        # Configure app logger
        app.logger.setLevel(logging.INFO)
        
        # Remove any existing handlers
        app.logger.handlers = []
        
        # Add handlers
        app.logger.addHandler(file_handler)
        app.logger.addHandler(console_handler)
        
        app.logger.info("Logging setup completed successfully")
    except Exception as e:
        print(f"Error setting up logging: {str(e)}")

# Create Flask app with explicit template and static folders
app = Flask(__name__,
            template_folder=os.path.join(BASE_DIR, 'templates'),
            static_folder=os.path.join(BASE_DIR, 'static'))

app.secret_key = os.urandom(24)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
app.register_blueprint(dashboard, url_prefix='/dashboard')

# Create a 1x1 transparent GIF pixel
PIXEL_GIF = base64.b64decode('R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7')

# Setup logging
setup_logging()

# Update database engine creation
def get_db_engine():
    db_url = f'sqlite:///{DB_PATH}'
    return sa.create_engine(db_url,
        pool_size=20,
        max_overflow=10,
        pool_recycle=300,
        pool_pre_ping=True
    )

# Add Redis-based caching initialization and error handling
from flask_caching import Cache

# Configure caching
cache = Cache(config={
    'CACHE_TYPE': 'RedisCache',
    'CACHE_REDIS_URL': 'redis://localhost:6379/0',
    'CACHE_DEFAULT_TIMEOUT': 300
})

try:
    cache.init_app(app)
    app.logger.info('Cache initialization successful')
except ConnectionError as e:
    app.logger.error(f'Cache connection failed: {str(e)}')
    # Fallback to simple in-memory cache
    cache = Cache(config={'CACHE_TYPE': 'SimpleCache'})
    cache.init_app(app)

# Error handlers
@app.errorhandler(404)
def not_found_error(error):
    if 'user_id' in session:
        flash('Page not found')
        return redirect(url_for('dashboard.index'))
    return redirect(url_for('login'))

@app.errorhandler(500)
def internal_error(error):
    flash('An internal error occurred')
    if 'user_id' in session:
        return redirect(url_for('dashboard.index'))
    return redirect(url_for('login'))

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Authentication decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in first')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or not session.get('is_admin'):
            flash('Admin access required')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

from threading import Lock

track_lock = Lock()

@app.route('/track/<campaign_id>/<recipient_id>')
def track(campaign_id, recipient_id):
    with track_lock:
        """Track email opens"""
        try:
            # Get tracking parameters
            sender = request.args.get('sender')
            
            if not campaign_id or not recipient_id or not sender:
                app.logger.error(f'Missing tracking parameters - Campaign: {campaign_id}, Recipient: {recipient_id}, Sender: {sender}')
                return send_file(
                    io.BytesIO(PIXEL_GIF),
                    mimetype='image/gif',
                    cache_control='no-cache, no-store, must-revalidate'
                )
            
            app.logger.info(f'Processing tracking request - Campaign: {campaign_id}, Recipient: {recipient_id}, Sender: {sender}')
            
            # Create database engine using the new function
            engine = get_db_engine()
            Base.metadata.create_all(engine)
            Session = sessionmaker(bind=engine)
            session = Session()
            
            try:
                # Find existing record
                existing_track = session.query(PixelTrack).filter(
                    PixelTrack.campaign_id == campaign_id,
                    PixelTrack.recipient == recipient_id,
                    PixelTrack.sender_email == sender
                ).first()
                
                if existing_track:
                    app.logger.info(f'Found existing tracking record - Campaign: {campaign_id}, Recipient: {recipient_id}, Sender: {sender}')
                    # Update existing record only if not already opened
                    if not existing_track.is_opened:
                        existing_track.is_opened = True
                        existing_track.opened_timestamp = datetime.utcnow()
                        existing_track.user_agent = request.headers.get('User-Agent', 'unknown')
                        existing_track.ip_address = request.remote_addr
                        session.commit()
                        app.logger.info(f'Updated tracking record - Campaign: {campaign_id}, Recipient: {recipient_id}, Sender: {sender}')
                    else:
                        app.logger.info(f'Email already tracked as opened - Campaign: {campaign_id}, Recipient: {recipient_id}, Sender: {sender}')
                else:
                    app.logger.warning(f'No tracking record found - Campaign: {campaign_id}, Recipient: {recipient_id}, Sender: {sender}')
                    # Create new record if none exists
                    track = PixelTrack(
                        id=str(uuid.uuid4()),
                        campaign_id=campaign_id,
                        recipient=recipient_id,
                        sender_email=sender,
                        is_opened=True,
                        opened_timestamp=datetime.utcnow(),
                        user_agent=request.headers.get('User-Agent', 'unknown'),
                        ip_address=request.remote_addr
                    )
                    session.add(track)
                    session.commit()
                    app.logger.info(f'Created new tracking record - Campaign: {campaign_id}, Recipient: {recipient_id}, Sender: {sender}')
            
            except Exception as e:
                app.logger.error(f'Database error while tracking: {str(e)}')
                session.rollback()
            finally:
                session.close()
                
            # Return tracking pixel with no-cache headers
            response = send_file(
                io.BytesIO(PIXEL_GIF),
                mimetype='image/gif',
                cache_timeout=0
            )
            response.headers['Cache-Control'] = 'no-store, max-age=0'
            return response
        
        except Exception as e:
            app.logger.error(f'Tracking error: {str(e)}')
            return send_file(
                io.BytesIO(PIXEL_GIF),
                mimetype='image/gif',
                cache_control='no-cache, no-store, must-revalidate'
            )

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard.index'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('dashboard.index'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if not username or not password:
            flash('Please enter both username and password')
            return render_template('login.html')
            
        result = authenticate_user(username, password)
        
        if result:
            user_id, is_admin = result
            session['user_id'] = user_id
            session['username'] = username
            session['is_admin'] = is_admin
            return redirect(url_for('dashboard.index'))
        
        flash('Invalid username or password')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out')
    return redirect(url_for('login'))

@app.route('/send_email', methods=['GET', 'POST'])
@login_required
def send_email():
    if request.method == 'POST':
        try:
            # Get form data
            sender_email = request.form.get('sender_email')
            sender_password = request.form.get('sender_password')
            subject = request.form.get('subject')
            body = request.form.get('body')
            recipients_method = request.form.get('recipients_method', 'manual')
            
            # Get recipients based on method
            if recipients_method == 'manual':
                recipients_text = request.form.get('recipients', '').strip()
                if not recipients_text:
                    flash('Please enter at least one recipient email address', 'error')
                    return render_template('send_email.html')
                recipients = [email.strip() for email in recipients_text.split(',') if email.strip()]
            else:  # file method
                if 'recipients_file' not in request.files:
                    flash('Please upload a recipients file', 'error')
                    return render_template('send_email.html')
                    
                file = request.files['recipients_file']
                if file.filename == '':
                    flash('No file selected', 'error')
                    return render_template('send_email.html')
                    
                # Read recipients from file
                recipients = []
                for line in file.read().decode('utf-8').splitlines():
                    email = line.strip()
                    if email:
                        recipients.append(email)
                        
            if not recipients:
                flash('No valid recipient email addresses found', 'error')
                return render_template('send_email.html')
                
            # Handle attachments
            attachments = []
            if 'attachments' in request.files:
                files = request.files.getlist('attachments')
                for file in files:
                    if file.filename:
                        filename = secure_filename(file.filename)
                        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                        file.save(filepath)
                        attachments.append(filepath)
            
            # Initialize EmailSender
            sender = EmailSender(
                username=sender_email,
                password=sender_password,
                tracking_server=request.url_root.rstrip('/')
            )
            
            # Generate campaign ID
            campaign_id = get_campaign_id()
            
            # Send emails
            success_count = 0
            error_messages = []
            
            for recipient in recipients:
                try:
                    success = sender.send_single_email(
                        recipient=recipient,
                        subject=subject,
                        body=body,
                        campaign_id=campaign_id,
                        attachments=attachments
                    )
                    if success:
                        success_count += 1
                    else:
                        error_messages.append(f"Failed to send email to {recipient}")
                except Exception as e:
                    error_messages.append(f"Error sending to {recipient}: {str(e)}")
            
            # Clean up attachment files
            for attachment in attachments:
                try:
                    os.remove(attachment)
                except:
                    pass
            
            # Flash appropriate messages
            if success_count == len(recipients):
                flash(f'Successfully sent emails to all {len(recipients)} recipients!', 'success')
            elif success_count > 0:
                flash(f'Partially successful: Sent {success_count} out of {len(recipients)} emails', 'warning')
                for error in error_messages:
                    flash(error, 'error')
            else:
                flash('Failed to send any emails', 'error')
                for error in error_messages:
                    flash(error, 'error')
            
            return redirect(url_for('dashboard.index'))
            
        except Exception as e:
            app.logger.error(f'Error in send_email: {str(e)}')
            flash(f'An error occurred: {str(e)}', 'error')
            return render_template('send_email.html')
    
    return render_template('send_email.html')

@app.route('/admin')
@admin_required
def admin_dashboard():
    stats = get_admin_stats()
    return render_template('admin_dashboard.html', stats=stats)

@app.route('/admin/users', methods=['GET', 'POST', 'DELETE'])
@admin_required
def manage_users():
    if request.method == 'POST':
        if not all(key in request.form for key in ['username', 'password', 'admin_password']):
            flash('Missing required fields')
            return render_template('manage_users.html')

        new_username = request.form['username']
        new_password = request.form['password']
        admin_password = request.form['admin_password']
        
        if create_user(session['username'], admin_password, new_username, new_password):
            flash('User created successfully')
        else:
            flash('Failed to create user')
            
    elif request.method == 'DELETE':
        if not all(key in request.form for key in ['username', 'admin_password']):
            flash('Missing required fields')
            return render_template('manage_users.html')

        username_to_delete = request.form['username']
        admin_password = request.form['admin_password']
        
        if username_to_delete == session['username']:
            flash('Cannot delete your own account')
            return render_template('manage_users.html')
        
        if delete_user(session['username'], admin_password, username_to_delete):
            flash('User deleted successfully')
        else:
            flash('Failed to delete user')
    
    return render_template('manage_users.html')

if __name__ == '__main__':
    # Ensure the database is initialized
    from db_setup import init_database
    init_database()
    
    # Create static folder if it doesn't exist
    os.makedirs(os.path.join(os.path.dirname(__file__), 'static'), exist_ok=True)
    
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=3000)
    args = parser.parse_args()
    
    # Run the app - force debug mode to false in production
    app.run(host='0.0.0.0', port=args.port, debug=True, use_reloader=True, reloader_type='stat')
