import datetime
import smtplib
import os
import threading
import uuid
import json
import sys
import signal
from datetime import datetime
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker
from pixel_tracker_py2 import Base, PixelTrack  # Add PixelTrack import
import base64
import re

# Debug print
print("Python Version:", sys.version)
print("Current Python Path:", sys.path)

try:
    import queue
except ImportError:
    import Queue as queue

from threading import Thread
import logging

# Attempt to import email MIME modules with fallback
try:
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    from email.mime.application import MIMEApplication
except ImportError:
    # Fallback for older Python versions
    from email.MIMEMultipart import MIMEMultipart
    from email.MIMEText import MIMEText
    from email.MIMEApplication import MIMEApplication

# Debug print
print("Modules imported successfully!")

# Configure logging
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# Global flag for interruption
STOP_THREADS = False

def signal_handler(signum, frame):
    """
    Handle keyboard interrupt and other signals
    """
    global STOP_THREADS
    STOP_THREADS = True
    print("\n\nInterrupt received. Stopping email sending...")
    sys.exit(0)

def get_campaign_id():
    """
    Generate campaign ID based on today's date
    """
    return datetime.now().strftime("%d %B")

class EmailSender(object):
    def __init__(self, username, password, max_workers=5, tracking_server=None):
        """
        Initialize email sender with SMTP credentials
        
        :param username: Email address to send from
        :param password: Email account password
        :param max_workers: Maximum number of concurrent email threads
        :param tracking_server: Optional tracking server URL
        """
        if not username or not password:
            raise ValueError("Email username and password are required")
            
        self.username = str(username).strip()
        self.password = password.strip()
        self.max_workers = max_workers
        self.sent_count = 0
        self.failed_count = 0
        self.lock = threading.Lock()
        self.queue = queue.Queue()
        self.results = []
        self.tracking_server = tracking_server or 'http://localhost:3000'
        self.error_messages = []
        
        # Simple domain extraction for SMTP settings
        try:
            self.domain = self.username.split('@')[-1].lower()
        except:
            self.domain = 'gmail.com'  # Default fallback
        
        print("Email sender initialization completed")  # Debug print

    def _get_smtp_connection(self):
        """
        Determine SMTP settings based on email provider
        
        :return: SMTP connection object
        """
        try:
            print(f"\nGetting SMTP settings for domain: '{self.domain}'")  # Debug print
            
            # SMTP settings for different providers
            smtp_settings = {
                'gmail.com': ('smtp.gmail.com', 587),
                'yahoo.com': ('smtp.mail.yahoo.com', 587),
                'hotmail.com': ('smtp.live.com', 587),
                'outlook.com': ('smtp.office365.com', 587),
                'aol.com': ('smtp.aol.com', 587),
                'rediffmail.com': ('smtp.rediffmail.com', 587),
                'rediff.com': ('smtp.rediffmail.com', 587),
                'rediffmailpro.com': ('smtp.rediffmailpro.com', 465),
                'beenetmunication.com': ('smtp.rediffmailpro.com', 465)
            }

            # Find matching SMTP settings or use domain as SMTP server
            if self.domain in smtp_settings:
                host, port = smtp_settings[self.domain]
                print(f"Found predefined SMTP settings - Host: {host}, Port: {port}")  # Debug print
            else:
                host = f"smtp.{self.domain}"
                port = 587
                print(f"Using default SMTP settings - Host: {host}, Port: {port}")  # Debug print
                
            print(f"Attempting SMTP connection to {host}:{port}")  # Debug print
            
            # First try STARTTLS
            try:
                print("Trying STARTTLS connection...")  # Debug print
                smtp = smtplib.SMTP(host, port, timeout=30)
                smtp.set_debuglevel(1)
                smtp.starttls()
                print("Attempting login with STARTTLS...")  # Debug print
                smtp.login(self.username, self.password)
                print("STARTTLS connection successful")  # Debug print
                return smtp
            except Exception as e:
                print(f"STARTTLS connection failed: {str(e)}")  # Debug print
                print("Trying SSL connection...")  # Debug print
                try:
                    smtp = smtplib.SMTP_SSL(host, 465, timeout=30)
                    smtp.set_debuglevel(1)
                    print("Attempting login with SSL...")  # Debug print
                    smtp.login(self.username, self.password)
                    print("SSL connection successful")  # Debug print
                    return smtp
                except Exception as ssl_error:
                    print(f"SSL connection failed: {str(ssl_error)}")  # Debug print
                    raise smtplib.SMTPAuthenticationError(-1, f"Failed to connect to SMTP server {host}. Error: {str(ssl_error)}")
                
        except Exception as e:
            print(f"SMTP connection error: {str(e)}")  # Debug print
            raise smtplib.SMTPAuthenticationError(-1, f"SMTP connection error: {str(e)}")

    def add_tracking_pixel(self, html_body, recipient, campaign_id):
        """
        Add tracking pixel to HTML email body
        
        :param html_body: Original HTML body
        :param recipient: Email recipient
        :param campaign_id: Campaign identifier
        :return: Modified HTML body with tracking pixel
        """
        # Build tracking URL using configured server
        tracking_url = f"{self.tracking_server}/track?campaign_id={campaign_id}&sender={self.username}&recipient={recipient}"
        pixel_tag = f'<img src="{tracking_url}" width="1" height="1" alt="" style="display:none">'
        
        # Add HTML wrapper if not present
        if '<html' not in html_body:
            html_body = f"""
            <html>
            <head></head>
            <body>
            {html_body}
            </body>
            </html>
            """
        
        if '</body>' in html_body:
            return html_body.replace('</body>', f'{pixel_tag}</body>')
        else:
            return html_body + pixel_tag

    def send_single_email(self, recipient, subject, body, campaign_id, attachments=None):
        """
        Send a single email
        
        :param recipient: Email address of recipient
        :param subject: Email subject
        :param body: Email body text
        :param campaign_id: Campaign identifier
        :param attachments: List of file paths to attach
        :return: Tuple of (success, error_message)
        """
        global STOP_THREADS
        if STOP_THREADS:
            return False, "Sending interrupted"

        logging.info(f"Starting to send email to {recipient}")
        smtp = None
        session = None
        try:
            # Create message
            msg = MIMEMultipart()
            msg['From'] = '"{}" <{}>'.format(self.username.split('@')[0].capitalize(), self.username)
            msg['To'] = recipient
            msg['Subject'] = subject

            # Add tracking pixel and attach body
            tracked_body = self.add_tracking_pixel(body, recipient, campaign_id)
            msg.attach(MIMEText(tracked_body, 'html'))

            # Attach files
            if attachments:
                for filepath in attachments:
                    if os.path.exists(filepath):
                        with open(filepath, 'rb') as file:
                            part = MIMEApplication(file.read(), Name=os.path.basename(filepath))
                            part['Content-Disposition'] = 'attachment; filename="{}"'.format(os.path.basename(filepath))
                            msg.attach(part)
                            logging.info(f"Attached file: {filepath}")
                    else:
                        logging.warning(f'Attachment file not found - {filepath}')

            # Get SMTP connection
            logging.info(f"Establishing SMTP connection for {recipient}")
            smtp = self._get_smtp_connection()
            
            # Send email
            logging.info(f"Sending email to {recipient}")
            smtp.sendmail(self.username, recipient, msg.as_string())
            logging.info(f"Email sent successfully to {recipient}")
            
            # Record sent email in tracking database
            engine = sa.create_engine('sqlite:///tracking.db')
            Base.metadata.create_all(engine)
            Session = sessionmaker(bind=engine)
            session = Session()
            
            try:
                logging.info(f"Recording email sent status for {recipient}")
                # Create new tracking record
                track = PixelTrack(
                    id=str(uuid.uuid4()),
                    campaign_id=campaign_id,
                    sender_email=self.username,
                    recipient=recipient,
                    is_sent=True,
                    sent_timestamp=datetime.utcnow(),
                    is_opened=False,
                    opened_timestamp=None,
                    user_agent=None,
                    ip_address=None
                )
                session.add(track)
                session.commit()
                logging.info(f'Email sent and tracked - Campaign: {campaign_id}, Sender: {self.username}, Recipient: {recipient}')
                
                # Thread-safe increment of sent count
                with self.lock:
                    self.sent_count += 1
                
                return True, None
                
            except Exception as e:
                error_msg = f'Database error while recording sent email: {str(e)}'
                logging.error(error_msg)
                session.rollback()
                with self.lock:
                    self.error_messages.append(error_msg)
                return False, error_msg
                
        except smtplib.SMTPAuthenticationError as e:
            error_msg = f"SMTP Authentication failed: {str(e)}"
            logging.error(error_msg)
            with self.lock:
                self.error_messages.append(error_msg)
            return False, error_msg
        except smtplib.SMTPException as e:
            error_msg = f"SMTP Error: {str(e)}"
            logging.error(error_msg)
            with self.lock:
                self.error_messages.append(error_msg)
            return False, error_msg
        except Exception as e:
            error_msg = f"Error sending email: {str(e)}"
            logging.error(error_msg)
            with self.lock:
                self.error_messages.append(error_msg)
            return False, error_msg
            
        finally:
            # Thread-safe increment of failed count if needed
            if not smtp or not session:
                with self.lock:
                    self.failed_count += 1
            
            # Close database session
            if session:
                try:
                    session.close()
                except Exception as e:
                    logging.error(f'Error closing database session: {str(e)}')
                
            # Close SMTP connection
            if smtp:
                try:
                    smtp.quit()
                except Exception as e:
                    logging.error(f'Error closing SMTP connection: {str(e)}')

    def worker(self):
        """
        Worker thread to process email queue
        """
        global STOP_THREADS
        while not STOP_THREADS:
            try:
                email_details = self.queue.get(timeout=1)
                if email_details is None:
                    break
                success, error = self.send_single_email(*email_details)
                with self.lock:
                    self.results.append((success, error))
                self.queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                error_msg = f"Worker thread error: {str(e)}"
                logging.error(error_msg)
                with self.lock:
                    self.results.append((False, error_msg))
                    self.error_messages.append(error_msg)
                break

    def send_emails_threaded(self, email_list):
        """
        Send multiple emails using thread pool
        
        :param email_list: List of tuples (recipient, subject, body, campaign_id, attachments)
        """
        global STOP_THREADS
        STOP_THREADS = False

        # Reset counters and results
        self.sent_count = 0
        self.failed_count = 0
        self.results = []
        self.error_messages = []

        # Create worker threads
        threads = []
        for _ in range(self.max_workers):
            t = Thread(target=self.worker)
            t.daemon = True
            t.start()
            threads.append(t)

        # Add emails to queue
        for email_details in email_list:
            if STOP_THREADS:
                break
            self.queue.put(email_details)

        # Add stop signals
        for _ in range(self.max_workers):
            self.queue.put(None)

        # Wait for all tasks to complete or interruption
        try:
            self.queue.join()
        except KeyboardInterrupt:
            STOP_THREADS = True
        finally:
            # Stop worker threads
            for t in threads:
                t.join(timeout=2)

        # Log summary
        logging.info('Email sending completed. Sent: {}, Failed: {}'.format(
            self.sent_count, self.failed_count))
        
        # Return comprehensive results
        return {
            'success_count': self.sent_count,
            'failure_count': self.failed_count,
            'total_count': len(email_list),
            'results': self.results,
            'error_messages': list(set(self.error_messages))  # Unique error messages
        }

email_queue = queue.Queue()

def process_queue():
    while True:
        email_data = email_queue.get()
        try:
            # Existing send logic
            EmailSender.send_single_email(**email_data)
        except Exception as e:
            logging.error(f'Async send failed: {str(e)}')
        email_queue.task_done()

# Start worker thread
Thread(target=process_queue, daemon=True).start()

def read_file_lines(filepath):
    """
    Read lines from a file, stripping whitespace and removing empty lines
    
    :param filepath: Path to the file
    :return: List of non-empty, stripped lines
    """
    try:
        with open(filepath, 'r') as file:
            return [line.strip() for line in file if line.strip()]
    except Exception as e:
        logging.error('Error reading file {}: {}'.format(filepath, e))
        return []

def parse_recipients(recipients_input, recipients_file=None):
    """
    Parse recipients from either manual input or file
    
    :param recipients_input: Comma-separated list of recipients
    :param recipients_file: Path to recipients file
    :return: List of recipient email addresses
    """
    recipients = []
    
    if recipients_file:
        recipients = read_file_lines(recipients_file)
    elif recipients_input:
        recipients = [r.strip() for r in recipients_input.split(',') if r.strip()]
        
    return list(set(recipients))  # Remove duplicates

def main():
    try:
        # Set up signal handling only in main thread
        signal.signal(signal.SIGINT, signal_handler)  # Ctrl+C
        signal.signal(signal.SIGTERM, signal_handler)  # Termination signal

        # Paths for input files
        accounts_file = input("Enter path to accounts file (username,password format): ").strip()
        recipients_file = input("Enter path to recipients file (one email per line): ").strip()
        
        # Read accounts
        accounts = []
        for line in read_file_lines(accounts_file):
            try:
                username, password = line.split(',', 1)
                accounts.append((username.strip(), password.strip()))
            except ValueError:
                logging.warning('Skipping invalid account line: {}'.format(line))
        
        if not accounts:
            print("No valid accounts found. Exiting.")
            return
        
        # Read recipients
        recipients = read_file_lines(recipients_file)
        
        if not recipients:
            print("No recipients found. Exiting.")
            return
        
        # Generate campaign ID based on current date
        campaign_id = get_campaign_id()
        
        # Prompt for email details
        subject = input("Enter email subject: ").strip()
        
        # Multiline body input
        print("Enter email body (type 'END' on a new line to finish):")
        body_lines = []
        while True:
            line = input()
            if line == 'END':
                break
            body_lines.append(line)
        body = '\n'.join(body_lines)
        
        # Get attachments
        attachments = []
        print("Enter attachment file paths (leave blank when done):")
        while True:
            attachment = input("Attachment path: ")
            if not attachment:
                break
            attachments.append(attachment)
        
        # Prepare tracking pixel
        tracking_pixel = '<img src="http://45.141.122.177:8080/track?campaign_id={}" width="1" height="1" style="display:none;">'.format(campaign_id)
        
        # Add tracking pixel to body
        full_body = body + '\n\n' + tracking_pixel
        
        # Prepare email list
        email_list = [(recipient, subject, full_body, campaign_id, attachments or None) for recipient in recipients]
        
        # Select accounts to use
        print("\nAvailable Accounts:")
        for i, (username, _) in enumerate(accounts, 1):
            print("{0}. {1}".format(i, username))
        
        # Get account selection
        while True:
            try:
                account_selection = input("\nEnter account numbers to use (comma-separated, e.g. 1,2,3): ")
                selected_accounts = [accounts[int(num.strip())-1] for num in account_selection.split(',')]
                break
            except (ValueError, IndexError):
                print("Invalid selection. Please try again.")
        
        # Send emails from selected accounts
        for username, password in selected_accounts:
            print("\nSending emails from {}".format(username))
            sender = EmailSender(username, password)
            results = sender.send_emails_threaded(email_list)
            print("\nEmail sending results:")
            for success, error in results['results']:
                if success:
                    print(f"Email sent successfully to {email_list[results['results'].index((success, error))][0]}")
                else:
                    print(f"Email sending failed to {email_list[results['results'].index((success, error))][0]}: {error}")
            print(f"\nTotal emails sent: {results['success_count']}")
            print(f"Total emails failed: {results['failure_count']}")
            print(f"Total emails attempted: {results['total_count']}")
            print(f"Error messages: {', '.join(results['error_messages'])}")

    except KeyboardInterrupt:
        print("\nEmail sending interrupted by user.")
    except Exception as e:
        logging.error('Unexpected error: {}'.format(e))

if __name__ == "__main__":
    main()
