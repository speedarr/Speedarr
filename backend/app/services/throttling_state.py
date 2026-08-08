"""
Persistence for the throttling on/off toggle (issue #78).

State lives in the Configuration key-value table under underscore-prefixed
keys: load_config_from_db() skips them and update_full_config() exempts them
from deletion, so routine settings saves cannot wipe the toggle state.
Callers own the session lifecycle and must commit after save/clear.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.configuration import Configuration

KEY_ENABLED = "_throttling_enabled"
KEY_UNTIL = "_throttling_disabled_until"
KEY_BY = "_throttling_disabled_by"


@dataclass
class ThrottlingState:
    disabled: bool
    disabled_until: Optional[datetime]
    disabled_by: Optional[str]


async def _upsert(db: AsyncSession, key: str, value: str) -> None:
    result = await db.execute(select(Configuration).where(Configuration.key == key))
    existing = result.scalar_one_or_none()
    if existing:
        existing.value = value
        existing.value_type = "string"
    else:
        db.add(Configuration(key=key, value=value, value_type="string"))


async def load_throttling_state(db: AsyncSession) -> ThrottlingState:
    """Effective state: an expired disable window reads as enabled."""
    result = await db.execute(
        select(Configuration).where(Configuration.key.in_([KEY_ENABLED, KEY_UNTIL, KEY_BY]))
    )
    rows = {row.key: row.value for row in result.scalars().all()}
    if rows.get(KEY_ENABLED, "true") == "true":
        return ThrottlingState(disabled=False, disabled_until=None, disabled_by=None)

    until: Optional[datetime] = None
    raw_until = rows.get(KEY_UNTIL, "")
    if raw_until:
        until = datetime.fromisoformat(raw_until)
        if until.tzinfo is None:
            until = until.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) >= until:
            return ThrottlingState(disabled=False, disabled_until=None, disabled_by=None)
    return ThrottlingState(disabled=True, disabled_until=until, disabled_by=rows.get(KEY_BY) or None)


async def save_throttling_disabled(
    db: AsyncSession, until: Optional[datetime], by: Optional[str]
) -> None:
    await _upsert(db, KEY_ENABLED, "false")
    await _upsert(db, KEY_UNTIL, until.isoformat() if until else "")
    await _upsert(db, KEY_BY, by or "")


async def clear_throttling_state(db: AsyncSession) -> None:
    await db.execute(
        delete(Configuration).where(Configuration.key.in_([KEY_ENABLED, KEY_UNTIL, KEY_BY]))
    )
