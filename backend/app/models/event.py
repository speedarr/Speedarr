"""
System event model.
"""
from datetime import datetime, date
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, Date, JSON
from app.database import Base


class SystemEvent(Base):
    """System events, errors, and warnings."""

    __tablename__ = "system_events"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)

    event_type = Column(String(50), nullable=False, index=True)  # error, warning, info
    category = Column(String(50), nullable=True)  # plex, qbittorrent, snmp, etc.

    message = Column(Text, nullable=False)
    details = Column(JSON, nullable=True)  # Changed from JSONB to JSON for SQLite compatibility

    # Resolution
    resolved = Column(Boolean, default=False)
    resolved_at = Column(DateTime, nullable=True)
    resolution_note = Column(Text, nullable=True)

    created_date = Column(Date, nullable=False, default=date.today, index=True)
