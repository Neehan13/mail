import base64
import logging
import os
import json
import datetime
import uuid
from flask import Flask, send_file, request, jsonify
import sqlalchemy as sa
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import OperationalError
import io
import pytz

# Database Setup
Base = declarative_base()

class PixelTrack(Base):
    __tablename__ = 'pixel_tracks'
    
    id = sa.Column(sa.String, primary_key=True)
    campaign_id = sa.Column(sa.String)
    sender_email = sa.Column(sa.String, nullable=True)  # Make nullable for backward compatibility
    recipient = sa.Column(sa.String, nullable=True)     # Make nullable for backward compatibility
    timestamp = sa.Column(sa.DateTime, default=datetime.datetime.utcnow)
    user_agent = sa.Column(sa.String, nullable=True)
    ip_address = sa.Column(sa.String, nullable=True)
    device_info = sa.Column(sa.String, nullable=True)   # Make nullable for backward compatibility
    location = sa.Column(sa.String, nullable=True)      # Make nullable for backward compatibility
    is_sent = sa.Column(sa.Boolean, default=False)      # Track if email was sent successfully
    is_opened = sa.Column(sa.Boolean, default=False)    # Track if email was opened
    sent_timestamp = sa.Column(sa.DateTime, nullable=True)  # When the email was sent
    opened_timestamp = sa.Column(sa.DateTime, nullable=True)  # When the email was opened

# Ensure log and tracking data can be stored in the current directory
current_dir = os.path.dirname(os.path.abspath(__file__))
log_path = os.path.join(current_dir, 'tracking_logs', 'pixel_tracking.log')
tracking_data_path = os.path.join(current_dir, 'tracking_logs', 'tracking_data.json')
db_path = os.path.join(current_dir, 'tracking.db')

# Ensure tracking_logs directory exists
if not os.path.exists(os.path.join(current_dir, 'tracking_logs')):
    os.makedirs(os.path.join(current_dir, 'tracking_logs'))

# Configure logging
logging.basicConfig(
    filename=log_path, 
    level=logging.INFO, 
    format='%(asctime)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# Create SQLAlchemy engine and session
engine = sa.create_engine('sqlite:///{}'.format(db_path))

def migrate_database():
    """
    Migrate database schema if needed
    """
    try:
        # Attempt to query existing table to check schema
        connection = engine.connect()
        connection.execute("PRAGMA table_info(pixel_tracks)")
        
        # Check for new columns
        try:
            connection.execute("SELECT sender_email FROM pixel_tracks LIMIT 1")
        except OperationalError:
            # Column doesn't exist, add it
            connection.execute("ALTER TABLE pixel_tracks ADD COLUMN sender_email TEXT")
        
        try:
            connection.execute("SELECT recipient FROM pixel_tracks LIMIT 1")
        except OperationalError:
            connection.execute("ALTER TABLE pixel_tracks ADD COLUMN recipient TEXT")
        
        try:
            connection.execute("SELECT device_info FROM pixel_tracks LIMIT 1")
        except OperationalError:
            connection.execute("ALTER TABLE pixel_tracks ADD COLUMN device_info TEXT")
        
        try:
            connection.execute("SELECT location FROM pixel_tracks LIMIT 1")
        except OperationalError:
            connection.execute("ALTER TABLE pixel_tracks ADD COLUMN location TEXT")
        
        connection.close()
    except Exception as e:
        logging.error('Database migration error: {}'.format(e))
        # If migration fails, recreate the table
        Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)

# Create tables and migrate if needed
migrate_database()
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)

# Create a 1x1 transparent GIF pixel
PIXEL_GIF = base64.b64decode('R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7')

app = Flask(__name__)

def get_device_info(user_agent):
    """
    Extract basic device information from user agent
    """
    user_agent = user_agent.lower()
    if 'mobile' in user_agent:
        return 'Mobile'
    elif 'tablet' in user_agent:
        return 'Tablet'
    elif 'windows' in user_agent or 'macintosh' in user_agent or 'linux' in user_agent:
        return 'Desktop'
    return 'Unknown'

def track_pixel():
    """
    Track email engagement with comprehensive data collection
    """
    # Generate unique tracking ID
    track_id = str(uuid.uuid4())
    
    # Get campaign ID and sender from request
    campaign_id = request.args.get('campaign_id', 'unknown')
    sender_email = request.args.get('sender', 'unknown')
    recipient = request.args.get('recipient', 'unknown')
    
    # Collect tracking information
    user_agent = request.headers.get('User-Agent', 'unknown')
    tracking_info = {
        'id': track_id,
        'campaign_id': campaign_id,
        'sender_email': sender_email,
        'recipient': recipient,
        'timestamp': datetime.datetime.utcnow().isoformat(),
        'user_agent': user_agent,
        'ip_address': request.remote_addr,
        'device_info': get_device_info(user_agent)
    }
    
    # Save to database
    session = Session()
    try:
        # Try to find existing record for this email
        existing_track = session.query(PixelTrack).filter(
            PixelTrack.campaign_id == campaign_id,
            PixelTrack.sender_email == sender_email,
            PixelTrack.recipient == recipient
        ).first()
        
        if existing_track:
            # Update existing record to mark as opened
            existing_track.is_opened = True
            existing_track.opened_timestamp = datetime.datetime.utcnow()
            existing_track.user_agent = tracking_info['user_agent']
            existing_track.ip_address = tracking_info['ip_address']
            existing_track.device_info = tracking_info['device_info']
        else:
            # Create new record
            pixel_track = PixelTrack(
                id=track_id,
                campaign_id=campaign_id,
                sender_email=sender_email,
                recipient=recipient,
                user_agent=tracking_info['user_agent'],
                ip_address=tracking_info['ip_address'],
                device_info=tracking_info['device_info'],
                is_opened=True,
                opened_timestamp=datetime.datetime.utcnow()
            )
            session.add(pixel_track)
            
        session.commit()
    except Exception as e:
        logging.error('Database tracking error: {}'.format(e))
        session.rollback()
    finally:
        session.close()
    
    # Log tracking
    logging.info('Pixel tracked: {}'.format(tracking_info))
    
    # Return transparent pixel
    return send_file(
        io.BytesIO(PIXEL_GIF),
        mimetype='image/gif'
    )

def get_tracking_stats():
    """
    Provide comprehensive tracking statistics
    """
    session = Session()
    try:
        # Aggregate tracking data
        stats = session.query(
            PixelTrack.campaign_id,
            sa.func.count(sa.distinct(PixelTrack.recipient)).label('unique_recipients'),
            sa.func.count(PixelTrack.id).label('total_opens'),
            sa.func.min(PixelTrack.timestamp).label('first_open'),
            sa.func.max(PixelTrack.timestamp).label('last_open')
        ).group_by(PixelTrack.campaign_id).all()
        
        # Convert to list of dictionaries
        stats_list = [
            {
                'campaign_id': stat[0],
                'unique_recipients': stat[1],
                'total_opens': stat[2],
                'first_open': stat[3],
                'last_open': stat[4]
            } for stat in stats
        ]
        
        return jsonify(stats_list)
    except Exception as e:
        logging.error('Error retrieving tracking stats: {}'.format(e))
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()

# Define routes
@app.route('/track')
def track():
    return track_pixel()

@app.route('/stats')
def stats():
    return get_tracking_stats()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True)
