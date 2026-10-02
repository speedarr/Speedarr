"""
Persistence for each torrent client's normal limits (audit T4-5).

qBittorrent, Transmission and Deluge keep only one limit, the one Speedarr writes, so the
limit a client goes back to when Speedarr lets go is recorded the first time Speedarr reads
it and kept across restarts and settings saves. Same scheme as temporary_limits_state: one
underscore-prefixed Configuration row that load_config_from_db() skips and
update_full_config() leaves alone. Callers own the session lifecycle and must commit after
save. SABnzbd and NZBGet keep their own saved cap and get no record.
"""
import json
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Optional

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.configuration import Configuration

KEY = "_client_baselines"
_FIELDS = ("url", "download_limit", "upload_limit", "captured_at")
_LIMITS = ("download_limit", "upload_limit")


def make_record(
    url: str, download_limit: float, upload_limit: float, now: Optional[datetime] = None
) -> Dict[str, Any]:
    """One client's record: limits in Mbps (0 = unlimited), the address read, and when."""
    return {
        "url": (url or "").rstrip("/"),
        "download_limit": float(download_limit),
        "upload_limit": float(upload_limit),
        "captured_at": (now or datetime.now(timezone.utc)).isoformat(),
    }


def _valid(entry: Any) -> bool:
    if not isinstance(entry, dict):
        return False
    if not isinstance(entry.get("url"), str) or not isinstance(entry.get("captured_at"), str):
        return False
    for field in _LIMITS:
        value = entry.get(field)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
            return False
    return True


async def load_baselines(db: AsyncSession) -> Dict[str, Dict[str, Any]]:
    """Every readable record; an absent or malformed row reads as empty, a bad entry is skipped."""
    result = await db.execute(select(Configuration).where(Configuration.key == KEY))
    row = result.scalar_one_or_none()
    if row is None:
        return {}
    try:
        data = json.loads(row.value)
        if not isinstance(data, dict):
            raise ValueError("payload is not an object")
    except (ValueError, TypeError) as err:
        logger.warning(f"Malformed client baselines in {KEY}: {err}; ignoring them")
        return {}
    records: Dict[str, Dict[str, Any]] = {}
    for client_id, entry in data.items():
        if _valid(entry):
            records[client_id] = {field: entry[field] for field in _FIELDS}
        else:
            logger.warning(f"Ignoring malformed baseline for {client_id} in {KEY}")
    return records


async def save_baselines(db: AsyncSession, records: Dict[str, Dict[str, Any]]) -> None:
    value = json.dumps(records)
    result = await db.execute(select(Configuration).where(Configuration.key == KEY))
    existing = result.scalar_one_or_none()
    if existing:
        existing.value = value
        existing.value_type = "json"
    else:
        db.add(Configuration(key=KEY, value=value, value_type="json"))


def prune_baselines(records: Dict[str, Dict[str, Any]], download_clients: Iterable[Any]) -> Dict[str, Dict[str, Any]]:
    """Keep a record while its id is configured (enabled or not) at the address it was read from."""
    urls = {c.id: (c.url or "").rstrip("/") for c in download_clients}
    return {
        client_id: record
        for client_id, record in records.items()
        if client_id in urls and urls[client_id] == (record["url"] or "").rstrip("/")
    }
