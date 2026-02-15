"""
Bandwidth metrics models.
"""
from datetime import datetime, date
from sqlalchemy import Column, Integer, Float, Boolean, DateTime, Date, Index
from app.database import Base


class BandwidthMetric(Base):
    """Time-series bandwidth metrics."""

    __tablename__ = "bandwidth_metrics"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, nullable=False, index=True)

    # Download bandwidth
    total_download_limit = Column(Float, nullable=True)
    qbittorrent_download_speed = Column(Float, nullable=True)
    qbittorrent_download_limit = Column(Float, nullable=True)
    sabnzbd_download_speed = Column(Float, nullable=True)
    sabnzbd_download_limit = Column(Float, nullable=True)
    nzbget_download_speed = Column(Float, nullable=True)
    nzbget_download_limit = Column(Float, nullable=True)
    transmission_download_speed = Column(Float, nullable=True)
    transmission_download_limit = Column(Float, nullable=True)
    deluge_download_speed = Column(Float, nullable=True)
    deluge_download_limit = Column(Float, nullable=True)

    # Upload bandwidth
    total_upload_limit = Column(Float, nullable=True)
    qbittorrent_upload_speed = Column(Float, nullable=True)
    qbittorrent_upload_limit = Column(Float, nullable=True)
    sabnzbd_upload_speed = Column(Float, nullable=True)
    sabnzbd_upload_limit = Column(Float, nullable=True)
    transmission_upload_speed = Column(Float, nullable=True)
    transmission_upload_limit = Column(Float, nullable=True)
    deluge_upload_speed = Column(Float, nullable=True)
    deluge_upload_limit = Column(Float, nullable=True)

    # Network (SNMP)
    snmp_download_speed = Column(Float, nullable=True)
    snmp_upload_speed = Column(Float, nullable=True)

    # Stream impact
    active_streams_count = Column(Integer, default=0)
    total_stream_bandwidth = Column(Float, default=0)  # Media file bitrate
    total_stream_actual_bandwidth = Column(Float, default=0)  # Actual network throughput

    # WAN/LAN stream split
    wan_streams_count = Column(Integer, nullable=True)
    wan_stream_bandwidth = Column(Float, nullable=True)
    lan_streams_count = Column(Integer, nullable=True)
    lan_stream_bandwidth = Column(Float, nullable=True)

    # State
    is_throttled = Column(Boolean, default=False)

    created_date = Column(Date, nullable=False, default=date.today, index=True)


class BandwidthMetricHourly(Base):
    """Aggregated hourly bandwidth metrics."""

    __tablename__ = "bandwidth_metrics_hourly"

    id = Column(Integer, primary_key=True, index=True)
    hour_timestamp = Column(DateTime, nullable=False, index=True)

    # Averages
    avg_download_speed = Column(Float, nullable=True)
    avg_upload_speed = Column(Float, nullable=True)
    avg_active_streams = Column(Float, nullable=True)

    # Maximums
    max_download_speed = Column(Float, nullable=True)
    max_upload_speed = Column(Float, nullable=True)
    max_active_streams = Column(Integer, nullable=True)

    # Throttle time
    minutes_throttled = Column(Integer, nullable=True)

    created_date = Column(Date, nullable=False, default=date.today)


class BandwidthMetricDaily(Base):
    """Aggregated daily bandwidth metrics."""

    __tablename__ = "bandwidth_metrics_daily"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, unique=True, nullable=False, index=True)

    # Averages
    avg_download_speed = Column(Float, nullable=True)
    avg_upload_speed = Column(Float, nullable=True)
    avg_active_streams = Column(Float, nullable=True)

    # Maximums
    max_download_speed = Column(Float, nullable=True)
    max_upload_speed = Column(Float, nullable=True)
    max_active_streams = Column(Integer, nullable=True)

    # Totals
    total_streams = Column(Integer, nullable=True)
    total_throttle_events = Column(Integer, nullable=True)
    hours_throttled = Column(Float, nullable=True)
