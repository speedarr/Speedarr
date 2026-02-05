"""
Data retention service for cleaning up old records.
"""
from datetime import datetime, timedelta, timezone
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete
from app.config import SpeedarrConfig
from app.models import StreamHistory, BandwidthMetric, BandwidthMetricHourly, BandwidthMetricDaily, ThrottleDecision, SystemEvent, Notification
from app.models.configuration import ConfigurationHistory
from app.database import checkpoint_wal


class RetentionService:
    """
    Manages data retention and cleanup of old records.
    """

    def __init__(self, config: SpeedarrConfig):
        self.config = config

    async def cleanup_old_data(self, db: AsyncSession):
        """Clean up old data based on retention policy."""
        retention_days = self.config.history.retention_days
        logger.info(f"Starting data retention cleanup (retention: {retention_days} days)")

        try:
            # Clean up all tables using the same retention period
            await self._cleanup_table(db, StreamHistory, retention_days)
            await self._cleanup_table(db, BandwidthMetric, retention_days)
            await self._cleanup_table(db, BandwidthMetricHourly, retention_days)
            await self._cleanup_date_column_table(db, BandwidthMetricDaily, "date", retention_days)
            await self._cleanup_table(db, ThrottleDecision, retention_days)
            await self._cleanup_table(db, SystemEvent, retention_days)
            await self._cleanup_table(db, Notification, retention_days)
            await self._cleanup_datetime_table(db, ConfigurationHistory, "changed_at", retention_days)

            await db.commit()
            logger.info("Data retention cleanup completed")

            # Run WAL checkpoint after cleanup to consolidate the database
            await checkpoint_wal()

        except Exception as e:
            logger.error(f"Error during data retention cleanup: {e}")
            await db.rollback()

    async def _cleanup_datetime_table(self, db: AsyncSession, model, column_name: str, retention_days: int):
        """Clean up old records using a DateTime column instead of Date."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)

        try:
            column = getattr(model, column_name)
            stmt = delete(model).where(column < cutoff)
            result = await db.execute(stmt)
            deleted_count = result.rowcount

            if deleted_count > 0:
                logger.info(f"Deleted {deleted_count} old records from {model.__tablename__}")

        except Exception as e:
            logger.error(f"Error cleaning up {model.__tablename__}: {e}")
            raise

    async def _cleanup_date_column_table(self, db: AsyncSession, model, column_name: str, retention_days: int):
        """Clean up old records using a named Date column instead of created_date."""
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=retention_days)

        try:
            column = getattr(model, column_name)
            stmt = delete(model).where(column < cutoff_date.date())
            result = await db.execute(stmt)
            deleted_count = result.rowcount

            if deleted_count > 0:
                logger.info(f"Deleted {deleted_count} old records from {model.__tablename__}")

        except Exception as e:
            logger.error(f"Error cleaning up {model.__tablename__}: {e}")
            raise

    async def _cleanup_table(self, db: AsyncSession, model, retention_days: int):
        """Clean up old records from a specific table."""
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=retention_days)

        try:
            stmt = delete(model).where(model.created_date < cutoff_date.date())
            result = await db.execute(stmt)
            deleted_count = result.rowcount

            if deleted_count > 0:
                logger.info(f"Deleted {deleted_count} old records from {model.__tablename__}")

        except Exception as e:
            logger.error(f"Error cleaning up {model.__tablename__}: {e}")
            raise
