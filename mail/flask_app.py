# Print Python and library path for debugging
import sys
print("Python executable: ", sys.executable)
print("Python version: ", sys.version)
print("Python path: ", sys.path)

# Add local site-packages to path
import site
site.main()

# Attempt to import SQLAlchemy
try:
    # Try multiple import methods
    try:
        import sqlalchemy as sa
    except ImportError:
        try:
            from sqlalchemy import *
        except ImportError:
            print("Failed to import SQLAlchemy. Attempting alternative import.")
            sys.path.append('/home/developer/.local/lib/python3.6/site-packages')
            import sqlalchemy as sa

    # Verify import
    print("SQLAlchemy version: ", sa.__version__)
    
    # Import related modules
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.ext.declarative import declarative_base
except Exception as e:
    print("SQLAlchemy import error: ", e)
    print("Sys path: ", sys.path)
    sys.exit(1)

# Attempt to import Pandas with fallback
try:
    import numpy as np  # Ensure numpy is imported first
    import pandas as pd
except ImportError:
    print("Pandas or Numpy not found. Using basic dictionary for data handling.")
    pd = None
    np = None

# Rest of the existing imports
import os
import logging
import threading
import Queue
import pytz
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from werkzeug.utils import secure_filename
import datetime
import sqlite3
from mailer import EmailSender, read_file_lines

# Tracking domain configuration
TRACKING_DOMAIN = os.environ.get('TRACKING_DOMAIN', 'http://45.141.122.177:8080')

# Create declarative base and session
Base = declarative_base()

# Define the PixelTrack class
class PixelTrack(Base):
    __tablename__ = 'pixel_tracks'
    
    id = sa.Column(sa.String, primary_key=True)
    campaign_id = sa.Column(sa.String)
    sender_email = sa.Column(sa.String)
    recipient = sa.Column(sa.String)
    timestamp = sa.Column(sa.DateTime)
    ip_address = sa.Column(sa.String)
    device_info = sa.Column(sa.String)

# Create engine and session
try:
    engine = sa.create_engine('sqlite:///tracking.db')
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
except Exception as e:
    print("Database initialization failed: {}".format(e))
    sys.exit(1)

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'  # Replace with a real secret key
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(__file__), 'uploads')
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

# India timezone
INDIA_TZ = pytz.timezone('Asia/Kolkata')

# Add contextmanager import
from contextlib import contextmanager

class DatabaseConnectionPool:
    def __init__(self, max_connections=5):
        """
        Initialize database connection pool
        """
        self.max_connections = max_connections
        self.connections = []
    
    @contextmanager
    def get_connection(self):
        """
        Context manager for database connections
        Simplified for Python 2.7 compatibility
        """
        # Check if we have available connections
        if not self.connections:
            # Create a new connection if under max limit
            if len(self.connections) < self.max_connections:
                conn = sqlite3.connect('tracking.db')
                self.connections.append(conn)
            else:
                # Reuse an existing connection
                conn = self.connections[0]
        else:
            # Get the first available connection
            conn = self.connections[0]
        
        try:
            yield conn
        except Exception as e:
            print 'Database connection error: {}'.format(e)
            # Remove problematic connection
            if conn in self.connections:
                self.connections.remove(conn)
        finally:
            # Do not close the connection, just return it to the pool
            if conn not in self.connections:
                self.connections.append(conn)
    
    def close_all_connections(self):
        """
        Close all database connections
        """
        for conn in self.connections:
            try:
                conn.close()
            except Exception as e:
                print 'Error closing connection: {}'.format(e)
        
        # Clear the connections list
        self.connections = []

# Initialize the connection pool
db_pool = DatabaseConnectionPool()

def create_tracking_database():
    """
    Create tracking database and table if not exists
    """
    try:
        with db_pool.get_connection() as conn:
            cursor = conn.cursor()
            
            # Create table if not exists
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS pixel_tracks (
                id TEXT PRIMARY KEY,
                campaign_id TEXT,
                sender_email TEXT,
                recipient TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                ip_address TEXT,
                user_agent TEXT
            )
            ''')
            
            conn.commit()
        return True
    except Exception as e:
        print('Error creating tracking database: {}'.format(e))
        return False

def load_tracking_data():
    """
    Load tracking data from SQLite database
    """
    try:
        with db_pool.get_connection() as conn:
            # If pandas is not available, return basic data
            if pd is None:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM pixel_tracks")
                columns = [column[0] for column in cursor.description]
                results = [dict(zip(columns, row)) for row in cursor.fetchall()]
                return results
            
            # Use pandas if available
            df = pd.read_sql_query("SELECT * FROM pixel_tracks", conn)
            return df
    except Exception as e:
        print('Error loading tracking data: {}'.format(e))
        return [] if pd is None else pd.DataFrame()

@app.route('/')
def index():
    """
    Main page with navigation
    """
    return render_template('index.html')

@app.route('/send_emails', methods=['GET', 'POST'])
def send_emails():
    """
    Email sending page
    """
    if request.method == 'POST':
        try:
            # Handle accounts file
            accounts_file = request.files['accounts_file']
            accounts_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(accounts_file.filename))
            accounts_file.save(accounts_path)
            
            # Read accounts
            with open(accounts_path, 'r') as f:
                accounts_content = f.readlines()
            accounts = [line.strip().split(',') for line in accounts_content if line.strip()]
            
            # Handle recipients file
            recipients_file = request.files['recipients_file']
            recipients_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(recipients_file.filename))
            recipients_file.save(recipients_path)
            
            # Read recipients
            with open(recipients_path, 'r') as f:
                recipients = [line.strip() for line in f if line.strip()]
            
            # Get form data
            subject = request.form['subject']
            body = request.form['body']
            selected_account = request.form['account']
            
            # Find selected account credentials
            account_creds = None
            for account in accounts:
                if account[0] == selected_account:
                    account_creds = account
                    break
            
            if not account_creds:
                flash('Selected account not found!', 'error')
                return redirect(url_for('send_emails'))
            
            # Generate campaign ID in specific format
            now = datetime.datetime.now(INDIA_TZ)
            campaign_id = now.strftime("%d %b %Y")  # Exactly as requested
            
            # Prepare tracking pixel
            email_list = []
            for recipient in recipients:
                tracking_pixel = '<img src="{}/track?campaign_id={}&sender={}&recipient={}" width="1" height="1" style="display:none;">'.format(
                    TRACKING_DOMAIN, campaign_id, account_creds[0], recipient
                )
                full_body = body + '\n\n' + tracking_pixel
                
                # Handle attachments
                attachments = request.files.getlist('attachments')
                attachment_paths = []
                for attachment in attachments:
                    if attachment.filename:
                        attachment_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(attachment.filename))
                        attachment.save(attachment_path)
                        attachment_paths.append(attachment_path)
                
                email_list.append((recipient, subject, full_body, campaign_id, attachment_paths or None))
            
            # Send emails
            sender = EmailSender(account_creds[0], account_creds[1])
            results = sender.send_emails_threaded(email_list)
            
            # Clean up uploaded files
            os.remove(accounts_path)
            os.remove(recipients_path)
            for path in attachment_paths:
                os.remove(path)
            
            # Count results
            successful = sum(1 for result in results if result[0])
            failed = len(results) - successful
            
            flash('Campaign sent! {} emails sent successfully, {} failed.'.format(successful, failed), 'success')
            return redirect(url_for('index'))
        
        except Exception as e:
            flash('Error sending emails: {}'.format(e), 'error')
            return redirect(url_for('send_emails'))
    
    # GET request: show send emails page
    return render_template('send_emails.html')

@app.route('/dashboard')
def dashboard():
    """
    Comprehensive campaign tracking dashboard
    """
    session = Session()
    try:
        # Campaign-level metrics
        campaign_metrics = session.query(
            PixelTrack.campaign_id,
            PixelTrack.sender_email,
            sa.func.count(sa.func.distinct(PixelTrack.recipient)).label('unique_recipients'),
            sa.func.count(PixelTrack.id).label('total_opens'),
            sa.func.min(PixelTrack.timestamp).label('first_open'),
            sa.func.max(PixelTrack.timestamp).label('last_open')
        ).group_by(
            PixelTrack.campaign_id, 
            PixelTrack.sender_email
        ).all()
        
        # Prepare campaign data
        campaign_data = []
        for stat in campaign_metrics:
            campaign_id = stat[0] or 'Unknown'
            sender_email = stat[1] or 'Unknown'
            unique_recipients = stat[2]
            total_opens = stat[3]
            first_open = stat[4]
            last_open = stat[5]
            
            # Calculate open rate
            open_rate = round(float(unique_recipients) / max(total_opens, 1) * 100, 2) if total_opens > 0 else 0
            
            # Calculate campaign duration
            campaign_duration = 0
            if first_open and last_open:
                duration_seconds = (last_open - first_open).total_seconds()
                campaign_duration = round(duration_seconds / 3600, 2)
            
            campaign_data.append({
                'Campaign ID': campaign_id,
                'Sender Email': sender_email,
                'Unique Recipients': unique_recipients,
                'Total Opens': total_opens,
                'Open Rate (%)': open_rate,
                'First Open': first_open.strftime('%Y-%m-%d %H:%M:%S') if first_open else 'N/A',
                'Last Open': last_open.strftime('%Y-%m-%d %H:%M:%S') if last_open else 'N/A',
                'Campaign Duration (Hours)': campaign_duration
            })
        
        # Detailed tracking data
        detailed_tracking = session.query(
            PixelTrack.campaign_id,
            PixelTrack.recipient,
            PixelTrack.timestamp,
            PixelTrack.ip_address,
            PixelTrack.device_info
        ).order_by(PixelTrack.timestamp.desc()).limit(100).all()
        
        detailed_data = []
        for stat in detailed_tracking:
            detailed_data.append({
                'Campaign ID': stat[0] or 'Unknown',
                'Recipient': stat[1] or 'Unknown',
                'Timestamp': stat[2].strftime('%Y-%m-%d %H:%M:%S'),
                'IP Address': stat[3],
                'Device': stat[4] or 'Unknown'
            })
        
        # Overall metrics
        total_campaigns = len(campaign_data)
        total_unique_recipients = sum([data['Unique Recipients'] for data in campaign_data])
        total_opens = sum([data['Total Opens'] for data in campaign_data])
        avg_open_rate = sum([data['Open Rate (%)'] for data in campaign_data]) / max(total_campaigns, 1)
        
        return render_template('campaign_dashboard.html', 
            campaign_metrics=campaign_data, 
            detailed_tracking=detailed_data,
            overall_metrics={
                'Total Campaigns': total_campaigns,
                'Total Unique Recipients': total_unique_recipients,
                'Total Opens': total_opens,
                'Average Open Rate (%)': round(avg_open_rate, 2)
            }
        )
    except Exception as e:
        # Log the error
        print 'Dashboard generation error: {}'.format(e)
        return render_template('error.html', error=str(e))
    finally:
        session.close()

@app.route('/campaign_details/<campaign_id>')
def campaign_details(campaign_id):
    """
    Detailed view for a specific campaign
    """
    try:
        with db_pool.get_connection() as conn:
            # Use pandas if available
            if pd is not None:
                df = pd.read_sql_query(
                    "SELECT * FROM pixel_tracks WHERE campaign_id = ?", 
                    conn, 
                    params=(campaign_id,)
                )
                
                # Convert timestamps to India timezone
                df['timestamp'] = pd.to_datetime(df['timestamp']).dt.tz_localize('UTC').dt.tz_convert(INDIA_TZ)
                
                campaign_details = df.to_dict('records')
                
                return render_template('campaign_details.html', 
                                       campaign_id=campaign_id,
                                       campaign_details=campaign_details)
            else:
                # Fallback for no pandas
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM pixel_tracks WHERE campaign_id = ?", (campaign_id,))
                columns = [column[0] for column in cursor.description]
                campaign_details = [dict(zip(columns, row)) for row in cursor.fetchall()]
                
                return render_template('campaign_details.html', 
                                       campaign_id=campaign_id,
                                       campaign_details=campaign_details)
    except Exception as e:
        flash('Error retrieving campaign details: {}'.format(e), 'error')
        return redirect(url_for('dashboard'))

if __name__ == '__main__':
    # Create tracking database before running
    create_tracking_database()
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Run the Flask app with minimal configuration
    try:
        print "Starting Flask application..."
        app.run(
            host='0.0.0.0', 
            port=5000, 
            debug=False  # Disable debug mode
        )
    except Exception as e:
        print "Error starting Flask application: {}".format(e)
