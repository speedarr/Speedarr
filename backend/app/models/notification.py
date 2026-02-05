"""
Notification model.
"""
from datetime import datetime, date
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, Date, JSON
from app.database import Base


class Notification(Base):
    """Sent notifications log."""

    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)

    event_type = Column(String(50), nullable=False, index=True)
    channel = Column(String(50), nullable=False)  # discord, webhook

    message = Column(Text, nullable=False)
    payload = Column(JSON, nullable=True)  # Changed from JSONB to JSON for SQLite compatibility

    # Delivery
    delivered = Column(Boolean, default=False)
    delivered_at = Column(DateTime, nullable=True)
    retry_count = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)

    created_date = Column(Date, nullable=False, default=date.today, index=True)
