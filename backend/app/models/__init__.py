"""
Database models for Speedarr.
"""
from app.models.user import User, APIToken
from app.models.configuration import Configuration
from app.models.stream import StreamHistory, ActiveStream
from app.models.bandwidth import BandwidthMetric, BandwidthMetricHourly, BandwidthMetricDaily
from app.models.decision import ThrottleDecision
from app.models.client import DownloadClient
from app.models.event import SystemEvent
from app.models.notification import Notification
from app.models.snmp import SNMPDevice

__all__ = [
    "User",
    "APIToken",
    "Configuration",
    "StreamHistory",
    "ActiveStream",
    "BandwidthMetric",
    "BandwidthMetricHourly",
    "BandwidthMetricDaily",
    "ThrottleDecision",
    "DownloadClient",
    "SystemEvent",
    "Notification",
    "SNMPDevice",
]
