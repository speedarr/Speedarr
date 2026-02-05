"""
Throttle decision model.
"""
from datetime import datetime, date
from sqlalchemy import Column, Integer, String, Text, Float, Boolean, DateTime, Date, JSON, ForeignKey
from app.database import Base


class ThrottleDecision(Base):
    """Throttle decision audit log."""

    __tablename__ = "throttle_decisions"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)

    # Decision
    decision_type = Column(String(20), nullable=False, index=True)  # throttle, restore, adjust
    reason = Column(Text, nullable=True)

    # Triggers
    active_streams = Column(Integer, default=0)
    stream_session_ids = Column(JSON, nullable=True)  # Changed from PG_ARRAY to JSON for SQLite compatibility
    total_required_bandwidth = Column(Float, nullable=True)

    # qBittorrent actions
    qbittorrent_old_download_limit = Column(Float, nullable=True)
    qbittorrent_new_download_limit = Column(Float, nullable=True)
    qbittorrent_old_upload_limit = Column(Float, nullable=True)
    qbittorrent_new_upload_limit = Column(Float, nullable=True)

    # SABnzbd actions
    sabnzbd_old_download_limit = Column(Float, nullable=True)
    sabnzbd_new_download_limit = Column(Float, nullable=True)
    sabnzbd_old_upload_limit = Column(Float, nullable=True)
    sabnzbd_new_upload_limit = Column(Float, nullable=True)

    # SNMP context
    snmp_download_usage = Column(Float, nullable=True)
    snmp_upload_usage = Column(Float, nullable=True)

    # Restoration
    restoration_scheduled_at = Column(DateTime, nullable=True)
    restoration_completed_at = Column(DateTime, nullable=True)
    restoration_cancelled = Column(Boolean, default=False)

    # Metadata
    triggered_by = Column(String(20), nullable=True)  # webhook, polling, manual
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    created_date = Column(Date, nullable=False, default=date.today, index=True)
