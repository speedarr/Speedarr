"""
SNMP device model.
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime
from app.database import Base


class SNMPDevice(Base):
    """SNMP monitoring device configuration."""

    __tablename__ = "snmp_devices"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)
    host = Column(String(255), nullable=False)
    port = Column(Integer, default=161)
    community = Column(String(100), default="public")
    version = Column(String(10), default="2c")

    # Interface to monitor
    interface_name = Column(String(100), nullable=True)
    oid_in = Column(String(255), nullable=True)
    oid_out = Column(String(255), nullable=True)

    is_enabled = Column(Boolean, default=True)
    is_connected = Column(Boolean, default=False)
    last_check = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
