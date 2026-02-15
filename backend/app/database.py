"""
Database connection and session management.

SQLite Scalability Notes:
-------------------------
This application uses SQLite with the following configuration for optimal performance:

1. WAL Mode (Write-Ahead Logging):
   - Enables concurrent reads during writes
   - Requires periodic checkpointing (handled by retention_service hourly)

2. NullPool:
   - Creates new connection for each operation (required for async SQLite)
   - SQLite handles concurrent access via file-level locking

3. Busy Timeout (5 seconds):
   - Prevents "database is locked" errors during concurrent access
   - Requests will wait up to 5s for locks to release

Limitations:
- Single-writer: Only one write transaction at a time
- File-based: All data must fit on local disk
- Recommended for deployments with < 50 concurrent users
- For higher scale, consider migrating to PostgreSQL

If you experience "database is locked" errors under load:
1. Increase busy_timeout in set_sqlite_pragma()
2. Reduce polling frequency in settings
3. Consider PostgreSQL for production deployments
"""
import sqlite3
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy.pool import NullPool
from sqlalchemy import event, text
from sqlalchemy.engine import Engine
from app.config import settings
from app.constants import SQLITE_BUSY_TIMEOUT_MS

# Create async engine
engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    poolclass=NullPool,
    future=True
)

# Create session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False
)

# Base class for models
Base = declarative_base()


# Enable SQLite foreign key constraints and WAL mode
@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_conn, connection_record):
    """
    Enable SQLite-specific optimizations when using SQLite.
    - PRAGMA foreign_keys=ON: Enable foreign key constraints (disabled by default in SQLite)
    - PRAGMA journal_mode=WAL: Use Write-Ahead Logging for better concurrency
    - PRAGMA busy_timeout=5000: Wait up to 5s for locks to release (prevents "database is locked" errors)
    - PRAGMA synchronous=NORMAL: Balance between safety and performance for WAL mode
    """
    if isinstance(dbapi_conn, sqlite3.Connection):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS}")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()


async def get_db() -> AsyncSession:
    """
    Dependency for getting database session.

    Usage:
        @router.get("/endpoint")
        async def endpoint(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """Initialize database tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Run migrations for any new columns
    await run_migrations()


async def run_migrations():
    """
    Run database migrations to add any missing columns.

    Note: SQLite ALTER TABLE only supports adding columns, not modifying/removing.
    Each migration runs within its own transaction for atomicity.
    """
    from loguru import logger

    # New columns to add to bandwidth_metrics table (for multi-client support)
    new_columns = [
        ("nzbget_download_speed", "REAL"),
        ("nzbget_download_limit", "REAL"),
        ("transmission_download_speed", "REAL"),
        ("transmission_download_limit", "REAL"),
        ("deluge_download_speed", "REAL"),
        ("deluge_download_limit", "REAL"),
        ("transmission_upload_speed", "REAL"),
        ("transmission_upload_limit", "REAL"),
        ("deluge_upload_speed", "REAL"),
        ("deluge_upload_limit", "REAL"),
        # WAN/LAN stream split
        ("wan_streams_count", "INTEGER"),
        ("wan_stream_bandwidth", "REAL"),
        ("lan_streams_count", "INTEGER"),
        ("lan_stream_bandwidth", "REAL"),
    ]

    try:
        async with engine.begin() as conn:
            # Get existing columns
            result = await conn.execute(text("PRAGMA table_info(bandwidth_metrics)"))
            existing_columns = {row[1] for row in result.fetchall()}

            # Add missing columns (each ALTER TABLE is auto-committed in SQLite)
            columns_added = 0
            for column_name, column_type in new_columns:
                if column_name not in existing_columns:
                    logger.info(f"Adding column '{column_name}' to bandwidth_metrics table")
                    await conn.execute(text(f"ALTER TABLE bandwidth_metrics ADD COLUMN {column_name} {column_type}"))
                    columns_added += 1

            if columns_added > 0:
                logger.info(f"Migration complete: added {columns_added} new column(s)")
            else:
                logger.debug("No migrations needed - all columns exist")

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        raise  # Re-raise to prevent app startup with inconsistent schema


async def checkpoint_wal():
    """
    Run a WAL checkpoint to consolidate the write-ahead log.
    Call this periodically (e.g., during retention cleanup) to prevent WAL file growth.
    """
    from loguru import logger
    try:
        async with engine.begin() as conn:
            await conn.execute(text("PRAGMA wal_checkpoint(TRUNCATE)"))
            logger.debug("WAL checkpoint completed")
    except Exception as e:
        logger.warning(f"WAL checkpoint failed: {e}")


async def close_db():
    """Close database connections."""
    # Run final checkpoint before closing
    await checkpoint_wal()
    await engine.dispose()
