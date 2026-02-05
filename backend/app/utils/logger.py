"""
Logging configuration using loguru.
"""
import sys
from pathlib import Path
from loguru import logger
from app.config import settings
from app.middleware.correlation import correlation_id_filter


def setup_logger():
    """Configure loguru logger with correlation ID support."""
    # Remove default handler
    logger.remove()

    # Add console handler with correlation ID
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <dim>{extra[correlation_id]}</dim> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level="DEBUG" if settings.debug else "INFO",
        colorize=True,
        filter=correlation_id_filter,
    )

    # Add file handler for log capture - writes to /data/logs for Docker persistence
    log_dir = Path("/data/logs")
    log_dir.mkdir(parents=True, exist_ok=True)

    logger.add(
        log_dir / "speedarr.log",
        rotation="10 MB",
        retention="7 days",
        level="INFO",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {extra[correlation_id]} | {name}:{function}:{line} - {message}",
        filter=correlation_id_filter,
    )

    logger.info("Logger initialized with correlation ID support")
