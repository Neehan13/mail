import sqlite3
import hashlib
from functools import wraps
import os
from typing import Optional, Tuple
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker
from pixel_tracker_py2 import Base, PixelTrack

# Define User model if not already defined
class User(Base):
    __tablename__ = 'users'
    id = sa.Column(sa.Integer, primary_key=True)
    username = sa.Column(sa.String, unique=True, nullable=False)
    password = sa.Column(sa.String, nullable=False)
    email = sa.Column(sa.String)
    is_admin = sa.Column(sa.Boolean, default=False)

def get_db_connection():
    """Get database connection"""
    db_path = os.path.join(os.path.dirname(__file__), 'mailer.db')
    return sqlite3.connect(db_path)

def hash_password(password: str) -> str:
    """Hash a password using SHA-256"""
    return hashlib.sha256(password.encode()).hexdigest()

def authenticate_user(username: str, password: str) -> Optional[Tuple[int, bool]]:
    """
    Authenticate a user and return (user_id, is_admin) if successful, None if not
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            'SELECT id, is_admin FROM users WHERE username = ? AND password = ?',
            (username, hash_password(password))
        )
        result = cursor.fetchone()
        return result if result else None
    finally:
        conn.close()

def create_user(admin_username: str, admin_password: str, new_username: str, new_password: str) -> bool:
    """
    Create a new user (admin only)
    Returns True if successful, False otherwise
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Verify admin credentials
        cursor.execute(
            'SELECT id FROM users WHERE username = ? AND password = ? AND is_admin = 1',
            (admin_username, hash_password(admin_password))
        )
        if not cursor.fetchone():
            return False
        
        # Create new user
        cursor.execute(
            'INSERT INTO users (username, password, is_admin) VALUES (?, ?, ?)',
            (new_username, hash_password(new_password), False)
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        # Username already exists
        return False
    finally:
        conn.close()

def delete_user(admin_username: str, admin_password: str, username_to_delete: str) -> bool:
    """
    Delete a user (admin only)
    Returns True if successful, False otherwise
    """
    if username_to_delete == 'admin':
        return False  # Prevent deletion of admin account
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Verify admin credentials
        cursor.execute(
            'SELECT id FROM users WHERE username = ? AND password = ? AND is_admin = 1',
            (admin_username, hash_password(admin_password))
        )
        if not cursor.fetchone():
            return False
        
        # Delete user
        cursor.execute('DELETE FROM users WHERE username = ? AND is_admin = 0', 
                      (username_to_delete,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()

def get_user_stats(user_id):
    """Get statistics for a specific user"""
    engine = sa.create_engine('sqlite:///tracking.db')
    Base.metadata.create_all(engine)  # Ensure tables exist
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        # Get user's email from user_id using SQLite connection
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT username FROM users WHERE id = ?', (user_id,))
        result = cursor.fetchone()
        if not result:
            raise ValueError(f"User not found with id {user_id}")
        user_email = result[0]
        conn.close()
        
        # Get campaign stats for this user using updated syntax
        stats = session.query(
            sa.func.count(sa.distinct(PixelTrack.campaign_id)).label('total_campaigns'),
            sa.func.count(sa.distinct(PixelTrack.recipient)).label('total_recipients'),
            sa.func.sum(sa.case(
                (PixelTrack.is_sent.is_(True), 1),
                else_=0
            )).label('total_sent'),
            sa.func.count(PixelTrack.id).label('total_opens')
        ).filter(PixelTrack.sender_email == user_email).first()
        
        # Handle None values
        total_sent = stats.total_sent or 0
        total_opens = stats.total_opens or 0
        
        return {
            'total_campaigns': stats.total_campaigns or 0,
            'total_recipients': stats.total_recipients or 0,
            'total_sent': total_sent,
            'total_opens': total_opens,
            'avg_open_rate': round((total_opens / max(total_sent, 1)) * 100, 1) if total_sent else 0
        }
    except Exception as e:
        print(f"Error getting user stats: {e}")
        return {
            'total_campaigns': 0,
            'total_recipients': 0,
            'total_sent': 0,
            'total_opens': 0,
            'avg_open_rate': 0
        }
    finally:
        session.close()

def get_admin_stats():
    """Get overall statistics for admin"""
    engine = sa.create_engine('sqlite:///tracking.db')
    Base.metadata.create_all(engine)  # Ensure tables exist
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        # Get overall stats using updated syntax
        stats = session.query(
            sa.func.count(sa.distinct(PixelTrack.campaign_id)).label('total_campaigns'),
            sa.func.count(sa.distinct(PixelTrack.recipient)).label('total_recipients'),
            sa.func.sum(sa.case(
                (PixelTrack.is_sent.is_(True), 1),
                else_=0
            )).label('total_sent'),
            sa.func.count(PixelTrack.id).label('total_opens')
        ).first()
        
        # Get user count from SQLite database
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM users')
        user_count = cursor.fetchone()[0]
        conn.close()
        
        # Handle None values
        total_sent = stats.total_sent or 0
        total_opens = stats.total_opens or 0
        
        return {
            'total_users': user_count,
            'total_campaigns': stats.total_campaigns or 0,
            'total_recipients': stats.total_recipients or 0,
            'total_sent': total_sent,
            'total_opens': total_opens,
            'avg_open_rate': round((total_opens / max(total_sent, 1)) * 100, 1) if total_sent else 0
        }
    except Exception as e:
        print(f"Error getting admin stats: {e}")
        return {
            'total_users': 0,
            'total_campaigns': 0,
            'total_recipients': 0,
            'total_sent': 0,
            'total_opens': 0,
            'avg_open_rate': 0
        }
    finally:
        session.close()