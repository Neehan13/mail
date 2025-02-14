from flask import Blueprint, render_template, jsonify
from datetime import datetime
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker
from pixel_tracker_py2 import Base, PixelTrack
import logging

dashboard = Blueprint('dashboard', __name__)

class DashboardManager:
    def __init__(self, db_path='tracking.db'):
        self.engine = sa.create_engine(f'sqlite:///{db_path}')
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

    def get_campaign_stats(self):
        session = self.Session()
        try:
            # Get campaign-level statistics using updated SQLAlchemy syntax
            campaign_stats = session.query(
                PixelTrack.campaign_id,
                PixelTrack.sender_email,
                sa.func.count(sa.distinct(PixelTrack.recipient)).label('unique_recipients'),
                sa.func.sum(sa.case(
                    (PixelTrack.is_sent.is_(True), 1),
                    else_=0
                )).label('total_sent'),
                sa.func.sum(sa.case(
                    (PixelTrack.is_opened.is_(True), 1),
                    else_=0
                )).label('total_opens'),
                sa.func.min(sa.case(
                    (PixelTrack.is_opened.is_(True), PixelTrack.opened_timestamp),
                    else_=None
                )).label('first_open'),
                sa.func.max(sa.case(
                    (PixelTrack.is_opened.is_(True), PixelTrack.opened_timestamp),
                    else_=None
                )).label('last_open')
            ).group_by(
                PixelTrack.campaign_id,
                PixelTrack.sender_email
            ).all()

            # Format campaign data
            campaigns = []
            total_recipients = 0
            total_sent = 0
            total_opens = 0

            for stat in campaign_stats:
                # Handle None values
                sent = stat.total_sent or 0
                opens = stat.total_opens or 0
                
                campaign = {
                    'id': stat.campaign_id,
                    'sender_email': stat.sender_email,
                    'recipients': stat.unique_recipients,
                    'total_sent': sent,
                    'total_opens': opens,
                    'open_rate': round((opens / max(sent, 1)) * 100, 1),
                    'first_open': stat.first_open.strftime('%Y-%m-%d %H:%M:%S') if stat.first_open else 'N/A',
                    'last_open': stat.last_open.strftime('%Y-%m-%d %H:%M:%S') if stat.last_open else 'N/A'
                }
                campaigns.append(campaign)
                total_recipients += stat.unique_recipients
                total_sent += sent
                total_opens += opens

            # Calculate overall statistics
            stats = {
                'total_campaigns': len(campaigns),
                'total_recipients': total_recipients,
                'total_sent': total_sent,
                'total_opens': total_opens,
                'avg_open_rate': round((total_opens / max(total_sent, 1)) * 100, 1)
            }

            return campaigns, stats

        except Exception as e:
            logging.error(f"Error getting campaign stats: {e}")
            return [], {
                'total_campaigns': 0,
                'total_recipients': 0,
                'total_sent': 0,
                'total_opens': 0,
                'avg_open_rate': 0
            }
        finally:
            session.close()

    def get_campaign_recipients(self, campaign_id):
        session = self.Session()
        try:
            # Get recipient-level statistics for the campaign using updated syntax
            recipient_stats = session.query(
                PixelTrack.recipient,
                sa.func.sum(sa.case(
                    (PixelTrack.is_sent.is_(True), 1),
                    else_=0
                )).label('sent'),
                sa.func.sum(sa.case(
                    (PixelTrack.is_opened.is_(True), 1),
                    else_=0
                )).label('opens'),
                sa.func.min(sa.case(
                    (PixelTrack.is_opened.is_(True), PixelTrack.opened_timestamp),
                    else_=None
                )).label('first_open'),
                sa.func.max(sa.case(
                    (PixelTrack.is_opened.is_(True), PixelTrack.opened_timestamp),
                    else_=None
                )).label('last_open')
            ).filter(
                PixelTrack.campaign_id == campaign_id
            ).group_by(
                PixelTrack.recipient
            ).all()

            # Format recipient data
            recipients = []
            for stat in recipient_stats:
                recipient = {
                    'email': stat.recipient,
                    'sent': stat.sent or 0,
                    'opens': stat.opens or 0,
                    'first_open': stat.first_open.strftime('%Y-%m-%d %H:%M:%S') if stat.first_open else 'N/A',
                    'last_open': stat.last_open.strftime('%Y-%m-%d %H:%M:%S') if stat.last_open else 'N/A'
                }
                recipients.append(recipient)

            return recipients

        except Exception as e:
            logging.error(f"Error getting campaign recipients: {e}")
            return []
        finally:
            session.close()

dashboard_manager = DashboardManager()

@dashboard.route('/')
def index():
    try:
        campaigns, stats = dashboard_manager.get_campaign_stats()
        return render_template('dashboard.html', campaigns=campaigns, stats=stats)
    except Exception as e:
        print(f"Error in dashboard index: {e}")
        return render_template('dashboard.html', campaigns=[], stats={
            'total_campaigns': 0,
            'total_recipients': 0,
            'total_sent': 0,
            'total_opens': 0,
            'avg_open_rate': 0
        })

@dashboard.route('/api/campaign/<campaign_id>/recipients')
def campaign_recipients(campaign_id):
    try:
        recipients = dashboard_manager.get_campaign_recipients(campaign_id)
        return jsonify({'recipients': recipients})
    except Exception as e:
        print(f"Error in campaign recipients: {e}")
        return jsonify({'recipients': []})
