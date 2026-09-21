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
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy.pool import NullPool
from sqlalchemy import event, text
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


def utcnow() -> datetime:
    """Naive UTC 'now' for DateTime column defaults.

    Replaces datetime.utcnow() (deprecated since Python 3.12). Stays naive on
    purpose: the SQLite DateTime type stores no offset and reads rows back as
    naive datetimes, so a naive default keeps freshly flushed objects and loaded
    rows comparable. Callers that need an aware value use datetime.now(timezone.utc).
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


# Enable SQLite foreign key constraints and WAL mode on every new connection.
# Registered on the async engine's sync_engine (the pattern SQLAlchemy documents for
# aiosqlite). The handler receives SQLAlchemy's AsyncAdapt_aiosqlite_connection, not a
# sqlite3.Connection, so it must not be gated on the DBAPI class (issue #88).
@event.listens_for(engine.sync_engine, "connect")
def set_sqlite_pragma(dbapi_conn, connection_record):
    """
    Enable SQLite-specific optimizations.
    - PRAGMA foreign_keys=ON: Enable foreign key constraints (disabled by default in SQLite)
    - PRAGMA journal_mode=WAL: Use Write-Ahead Logging for better concurrency
    - PRAGMA busy_timeout=5000: Wait up to 5s for locks to release (prevents "database is locked" errors)
    - PRAGMA synchronous=NORMAL: Balance between safety and performance for WAL mode
    """
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

    # Report the effective mode once; WAL silently fails to take on some filesystems (issue #88)
    log_sqlite_mode(await sqlite_mode())


_SYNCHRONOUS_NAMES = {0: "off", 1: "normal", 2: "full", 3: "extra"}


async def sqlite_mode(target: Optional[AsyncEngine] = None) -> dict:
    """Effective journal_mode / foreign_keys / synchronous of a fresh connection (app engine by default)."""
    if target is None:
        target = engine
    async with target.connect() as conn:
        return {
            pragma: (await conn.execute(text(f"PRAGMA {pragma}"))).scalar()
            for pragma in ("journal_mode", "foreign_keys", "synchronous")
        }


def log_sqlite_mode(mode: dict) -> None:
    """Log the effective SQLite settings once at startup; WARNING when WAL did not take.

    SQLite keeps the delete journal on filesystems without shared-memory support
    (network mounts), and `PRAGMA journal_mode=WAL` reports that silently.
    """
    from loguru import logger

    line = (
        f"SQLite journal_mode={mode['journal_mode']} "
        f"foreign_keys={'on' if mode['foreign_keys'] else 'off'} "
        f"synchronous={_SYNCHRONOUS_NAMES.get(mode['synchronous'], mode['synchronous'])}"
    )
    if mode["journal_mode"] == "wal":
        logger.info(line)
    else:
        logger.warning(f"{line} (WAL did not take; is /data on a network filesystem?)")


async def run_migrations():
    """
    Run database migrations to add any missing columns.

    Note: SQLite ALTER TABLE only supports adding columns, not modifying/removing.
    Each migration runs within its own transaction for atomicity.
    """
    from loguru import logger

    migrations = {
        "bandwidth_metrics": [
            ("nzbget_download_speed", "REAL"), ("nzbget_download_limit", "REAL"),
            ("transmission_download_speed", "REAL"), ("transmission_download_limit", "REAL"),
            ("deluge_download_speed", "REAL"), ("deluge_download_limit", "REAL"),
            ("transmission_upload_speed", "REAL"), ("transmission_upload_limit", "REAL"),
            ("deluge_upload_speed", "REAL"), ("deluge_upload_limit", "REAL"),
            ("wan_streams_count", "INTEGER"), ("wan_stream_bandwidth", "REAL"),
            ("lan_streams_count", "INTEGER"), ("lan_stream_bandwidth", "REAL"),
            # Media server abstraction
            ("per_server", "TEXT"),
            # Per-client-id bandwidth breakdown
            ("per_client", "TEXT"),
        ],
        "throttle_decisions": [
            ("per_client", "TEXT"),
        ],
        "stream_history": [
            ("server_id", "VARCHAR(100)"), ("server_name", "VARCHAR(100)"), ("server_type", "VARCHAR(20)"),
        ],
        "active_streams": [
            ("server_id", "VARCHAR(100)"), ("server_name", "VARCHAR(100)"), ("server_type", "VARCHAR(20)"),
        ],
    }

    try:
        async with engine.begin() as conn:
            total_added = 0
            for table, columns in migrations.items():
                result = await conn.execute(text(f"PRAGMA table_info({table})"))
                existing = {row[1] for row in result.fetchall()}
                for column_name, column_type in columns:
                    if column_name not in existing:
                        logger.info(f"Adding column '{column_name}' to {table}")
                        await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column_name} {column_type}"))
                        total_added += 1
            if total_added:
                logger.info(f"Migration complete: added {total_added} new column(s)")
            else:
                logger.debug("No migrations needed - all columns exist")
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        raise


async def checkpoint_wal(target: Optional[AsyncEngine] = None) -> Optional[tuple]:
    """
    Run a WAL checkpoint to consolidate the write-ahead log.
    Call this periodically (e.g., during retention cleanup) to prevent WAL file growth.

    Returns SQLite's (busy, log_pages, checkpointed) row, or None if the statement failed.
    TRUNCATE resets the log before reporting, so a successful run is (0, 0, 0);
    (1, n, m) means readers blocked the reset; (0, -1, -1) means the database is not in WAL mode.
    """
    from loguru import logger

    if target is None:
        target = engine
    try:
        async with target.begin() as conn:
            busy, log_pages, checkpointed = (await conn.execute(text("PRAGMA wal_checkpoint(TRUNCATE)"))).one()
        logger.debug(f"WAL checkpoint: busy={busy} log_pages={log_pages} checkpointed={checkpointed}")
        return busy, log_pages, checkpointed
    except Exception as e:
        logger.warning(f"WAL checkpoint failed: {e}")
        return None


async def close_db():
    """Close database connections."""
    # Run final checkpoint before closing
    await checkpoint_wal()
    await engine.dispose()
