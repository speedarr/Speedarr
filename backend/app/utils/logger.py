"""
Logging configuration using loguru.

Both sinks are added at the lowest level and share one filter, so the level can
change while the app runs: Settings › General › Log Level calls set_log_level()
on save and at startup (#103). DEBUG=true in the environment forces DEBUG
whatever the setting says.
"""
import sys
from pathlib import Path
from loguru import logger
from app.config import settings, LOG_LEVELS
from app.middleware.correlation import correlation_id_filter

DEFAULT_LOG_DIR = Path("/data/logs")

_LEVEL_NO = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}
_configured_level = "INFO"


def current_log_level() -> str:
    """The level the sinks apply: DEBUG when the DEBUG env var is set, else the configured level."""
    return "DEBUG" if settings.debug else _configured_level


def set_log_level(level: str) -> str:
    """Apply a configured level (one of LOG_LEVELS, any case). Returns the effective level."""
    global _configured_level
    name = str(level).upper()
    if name not in LOG_LEVELS:
        raise ValueError(f"Unknown log level {level!r}; expected one of {', '.join(LOG_LEVELS)}")
    _configured_level = name
    return current_log_level()


def _record_filter(record) -> bool:
    """Stamp the correlation id, then keep the record only if it reaches the current level."""
    correlation_id_filter(record)
    return record["level"].no >= _LEVEL_NO[current_log_level()]


def setup_logger(log_dir: Path = DEFAULT_LOG_DIR):
    """Configure loguru with a console sink and a rotating file sink under log_dir."""
    # Remove default handler
    logger.remove()

    # Console handler with correlation ID
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <dim>{extra[correlation_id]}</dim> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level=0,
        colorize=True,
        filter=_record_filter,
    )

    # File handler for log capture - /data/logs persists across container restarts
    log_dir.mkdir(parents=True, exist_ok=True)

    logger.add(
        log_dir / "speedarr.log",
        rotation="10 MB",
        retention="7 days",
        level=0,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {extra[correlation_id]} | {name}:{function}:{line} - {message}",
        filter=_record_filter,
    )

    logger.info(f"Logger initialized at {current_log_level()} with correlation ID support")
