"""
Persistence for temporary bandwidth limits (issue #108).

Same scheme as throttling_state: the limits live in the Configuration
key-value table under one underscore-prefixed key, which load_config_from_db()
skips and update_full_config() leaves alone, so a routine settings save cannot
wipe them. Callers own the session lifecycle and must commit after save/clear.
"""
import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from loguru import logger
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.configuration import Configuration

KEY = "_temporary_limits"
_FIELDS = ("download_mbps", "upload_mbps", "expires_at", "set_by", "set_at", "source")
_DATETIME_FIELDS = ("expires_at", "set_at")


def _parse_datetime(raw: Any) -> Optional[datetime]:
    """ISO string -> aware UTC datetime; None or '' -> None. Raises ValueError if malformed."""
    if raw in (None, ""):
        return None
    if not isinstance(raw, str):
        raise ValueError(f"expected an ISO timestamp, got {type(raw).__name__}")
    value = datetime.fromisoformat(raw)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value


async def load_temporary_limits(db: AsyncSession) -> Optional[Dict[str, Any]]:
    """Effective limits: None when absent, expired or unreadable."""
    result = await db.execute(select(Configuration).where(Configuration.key == KEY))
    row = result.scalar_one_or_none()
    if row is None:
        return None
    try:
        data = json.loads(row.value)
        if not isinstance(data, dict):
            raise ValueError("payload is not an object")
        limits = {field: data.get(field) for field in _FIELDS}
        for field in _DATETIME_FIELDS:
            limits[field] = _parse_datetime(limits[field])
    except (ValueError, TypeError) as err:
        logger.warning(f"Malformed temporary limits in {KEY}: {err}; ignoring the stored limit")
        return None
    expires_at = limits["expires_at"]
    if expires_at is not None and datetime.now(timezone.utc) >= expires_at:
        return None
    return limits


async def save_temporary_limits(db: AsyncSession, limits: Dict[str, Any]) -> None:
    payload = {field: limits.get(field) for field in _FIELDS}
    for field in _DATETIME_FIELDS:
        value = payload[field]
        payload[field] = value.isoformat() if isinstance(value, datetime) else None
    value = json.dumps(payload)
    result = await db.execute(select(Configuration).where(Configuration.key == KEY))
    existing = result.scalar_one_or_none()
    if existing:
        existing.value = value
        existing.value_type = "json"
    else:
        db.add(Configuration(key=KEY, value=value, value_type="json"))


async def clear_temporary_limits(db: AsyncSession) -> None:
    await db.execute(delete(Configuration).where(Configuration.key == KEY))
