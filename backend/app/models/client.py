"""
Download client model.
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime
from app.database import Base


class DownloadClient(Base):
    """Download client status and metadata."""

    __tablename__ = "download_clients"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), unique=True, nullable=False)
    type = Column(String(50), nullable=False)  # torrent, usenet

    # Connection
    url = Column(String(255), nullable=False)
    is_enabled = Column(Boolean, default=True)
    is_connected = Column(Boolean, default=False)
    last_connection_check = Column(DateTime, nullable=True)

    # Original limits
    original_download_limit = Column(Float, nullable=True)
    original_upload_limit = Column(Float, nullable=True)

    # Current state
    current_download_speed = Column(Float, nullable=True)
    current_upload_speed = Column(Float, nullable=True)
    current_download_limit = Column(Float, nullable=True)
    current_upload_limit = Column(Float, nullable=True)

    active_downloads = Column(Integer, default=0)
    queue_size = Column(Integer, default=0)

    # Metadata
    version = Column(String(50), nullable=True)
    last_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
