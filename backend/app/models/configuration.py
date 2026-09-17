"""
Configuration storage model.
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base, utcnow


class Configuration(Base):
    """Configuration key-value storage."""

    __tablename__ = "configuration"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(100), unique=True, nullable=False, index=True)
    value = Column(Text, nullable=False)
    value_type = Column(String(20), nullable=False)  # string, integer, float, boolean, json
    description = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)
    updated_by = Column(Integer, ForeignKey("users.id"), nullable=True)


class ConfigurationHistory(Base):
    """Audit trail for configuration changes."""

    __tablename__ = "configuration_history"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(100), nullable=False, index=True)
    old_value = Column(Text, nullable=True)
    new_value = Column(Text, nullable=False)
    value_type = Column(String(20), nullable=False)
    changed_at = Column(DateTime, default=utcnow, nullable=False, index=True)
    changed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
