import sqlite3
import hashlib
import os

def hash_password(password):
    """Hash a password using SHA-256"""
    return hashlib.sha256(password.encode()).hexdigest()

def init_database():
    """Initialize the database with required tables"""
    # Create database file in the same directory as this script
    db_path = os.path.join(os.path.dirname(__file__), 'mailer.db')
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Create users table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        is_admin BOOLEAN DEFAULT FALSE
    )
    ''')

    # Create email_logs table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS email_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        recipient TEXT NOT NULL,
        subject TEXT NOT NULL,
        sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        campaign_id TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )
    ''')

    # Create tracker_logs table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS tracker_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email_id INTEGER,
        event_type TEXT NOT NULL,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        ip_address TEXT,
        FOREIGN KEY (email_id) REFERENCES email_logs(id)
    )
    ''')

    # Create default admin user if not exists
    cursor.execute('SELECT * FROM users WHERE username = ?', ('admin',))
    if not cursor.fetchone():
        admin_password = hash_password('admin')
        cursor.execute(
            'INSERT INTO users (username, password, is_admin) VALUES (?, ?, ?)',
            ('admin', admin_password, True)
        )

    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_database()
    print("Database initialized successfully!")