"""
Stream models for historical and active streams.
"""
from datetime import datetime, date
from sqlalchemy import Column, Integer, String, Float, DateTime, Date, Index
from app.database import Base


class StreamHistory(Base):
    """Historical stream data."""

    __tablename__ = "stream_history"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(100), nullable=False, index=True)
    session_key = Column(String(100), nullable=True)

    # User info
    user_name = Column(String(100), nullable=True, index=True)
    user_id = Column(String(50), nullable=True)

    # Media info
    media_type = Column(String(20), nullable=True)
    media_title = Column(String(500), nullable=True)
    parent_title = Column(String(500), nullable=True)
    grandparent_title = Column(String(500), nullable=True)
    year = Column(Integer, nullable=True)

    # Stream details
    stream_bandwidth_mbps = Column(Float, nullable=True)
    quality_profile = Column(String(50), nullable=True)
    transcode_decision = Column(String(50), nullable=True)
    video_codec = Column(String(20), nullable=True)
    container = Column(String(20), nullable=True)

    # Timing
    started_at = Column(DateTime, nullable=False, index=True)
    ended_at = Column(DateTime, nullable=True, index=True)
    duration_seconds = Column(Integer, nullable=True)
    progress_seconds = Column(Integer, nullable=True)

    # Metadata
    player = Column(String(100), nullable=True)
    platform = Column(String(50), nullable=True)
    ip_address = Column(String(45), nullable=True)

    created_date = Column(Date, nullable=False, default=date.today, index=True)

    __table_args__ = (
        Index('idx_stream_history_dates', 'started_at', 'ended_at'),
    )


class ActiveStream(Base):
    """Currently active streams."""

    __tablename__ = "active_streams"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(100), unique=True, nullable=False, index=True)
    session_key = Column(String(100), nullable=True)

    # User info
    user_name = Column(String(100), nullable=True)
    user_id = Column(String(50), nullable=True)

    # Media info
    media_type = Column(String(20), nullable=True)
    media_title = Column(String(500), nullable=True)
    parent_title = Column(String(500), nullable=True)
    grandparent_title = Column(String(500), nullable=True)

    # Stream details
    stream_bandwidth_mbps = Column(Float, nullable=True)
    quality_profile = Column(String(50), nullable=True)
    transcode_decision = Column(String(50), nullable=True)
    state = Column(String(20), nullable=True)  # playing, paused, buffering

    # Timing
    started_at = Column(DateTime, nullable=False)
    last_seen_at = Column(DateTime, nullable=False, index=True)
    duration_seconds = Column(Integer, nullable=True)
    progress_seconds = Column(Integer, nullable=True)

    # Calculated
    restoration_delay_seconds = Column(Integer, nullable=True)

    # Metadata
    player = Column(String(100), nullable=True)
    platform = Column(String(50), nullable=True)
    ip_address = Column(String(45), nullable=True)
