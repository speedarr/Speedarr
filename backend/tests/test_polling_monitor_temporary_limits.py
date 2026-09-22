"""Temporary limits survive a restart and clear their row on expiry (issue #108)."""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.configuration import Configuration
from app.services.polling_monitor import PollingMonitor
from app.services.temporary_limits_state import KEY, save_temporary_limits, load_temporary_limits
from tests.conftest import make_config


@pytest.fixture
async def maker():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


def _monitor(get_db_session):
    pm = PollingMonitor.__new__(PollingMonitor)   # bypass __init__/network
    pm.config = make_config()
    pm.notification_service = None
    pm._get_db_session = get_db_session
    pm._temporary_limits = None
    pm._temporary_limits_lock = asyncio.Lock()
    pm._throttling_disabled = False
    pm._throttling_disabled_until = None
    pm._throttling_disabled_by = None
    pm._throttling_state_lock = asyncio.Lock()
    pm._reservations = []
    pm._reservations_lock = asyncio.Lock()
    pm.media_servers = {}
    pm._running = False
    pm._download_task = None
    pm._plex_task = None
    return pm


def _limits(expires_at):
    return {
        "download_mbps": 40.0,
        "upload_mbps": 8.0,
        "expires_at": expires_at,
        "set_by": "API: Unraid",
        "set_at": datetime.now(timezone.utc),
        "source": "parity check",
    }


async def _seed(maker, limits):
    async with maker() as db:
        await save_temporary_limits(db, limits)
        await db.commit()


async def _row_count(maker):
    async with maker() as db:
        rows = (await db.execute(select(Configuration).where(Configuration.key == KEY))).scalars().all()
        return len(rows)


async def test_load_restores_active_limits(maker):
    until = datetime.now(timezone.utc) + timedelta(hours=1)
    await _seed(maker, _limits(until))
    pm = _monitor(maker)
    await pm.load_temporary_limits_from_db()
    assert pm._temporary_limits["download_mbps"] == 40.0
    assert pm._temporary_limits["set_by"] == "API: Unraid"
    assert pm._temporary_limits["source"] == "parity check"
    assert pm._temporary_limits["expires_at"].tzinfo is not None
    assert await pm.get_active_temporary_limits() == (40.0, 8.0)


async def test_load_restores_indefinite_limits(maker):
    await _seed(maker, _limits(None))
    pm = _monitor(maker)
    await pm.load_temporary_limits_from_db()
    assert pm._temporary_limits["expires_at"] is None
    assert await pm.get_active_temporary_limits() == (40.0, 8.0)


async def test_load_skips_expired_row(maker):
    past = datetime.now(timezone.utc) - timedelta(minutes=1)
    await _seed(maker, _limits(past))
    pm = _monitor(maker)
    await pm.load_temporary_limits_from_db()
    assert pm._temporary_limits is None
    assert await pm.get_active_temporary_limits() == (None, None)


async def test_load_without_db_session_is_noop():
    pm = _monitor(None)
    await pm.load_temporary_limits_from_db()
    assert pm._temporary_limits is None


async def test_start_loads_persisted_limits(maker):
    """start() must restore the limits before the poll loops begin."""
    await _seed(maker, _limits(None))
    pm = _monitor(maker)

    async def noop():
        return None

    pm._download_poll_loop = noop
    pm._plex_poll_loop = noop
    pm.load_throttling_state_from_db = noop
    await pm.start()
    try:
        assert pm._temporary_limits is not None
        assert pm._temporary_limits["download_mbps"] == 40.0
    finally:
        await pm.stop()


async def test_expiry_during_poll_clears_row(maker):
    past = datetime.now(timezone.utc) - timedelta(seconds=1)
    await _seed(maker, _limits(past))
    pm = _monitor(maker)
    pm._temporary_limits = _limits(past)
    assert await pm.get_active_temporary_limits() == (None, None)
    assert pm._temporary_limits is None
    assert await _row_count(maker) == 0


async def test_expiry_without_db_session_still_clears_memory():
    past = datetime.now(timezone.utc) - timedelta(seconds=1)
    pm = _monitor(None)
    pm._temporary_limits = _limits(past)
    assert await pm.get_active_temporary_limits() == (None, None)
    assert pm._temporary_limits is None


async def test_active_limits_leave_row_alone(maker):
    until = datetime.now(timezone.utc) + timedelta(hours=1)
    await _seed(maker, _limits(until))
    pm = _monitor(maker)
    pm._temporary_limits = _limits(until)
    assert await pm.get_active_temporary_limits() == (40.0, 8.0)
    assert await _row_count(maker) == 1
    async with maker() as db:
        assert (await load_temporary_limits(db))["download_mbps"] == 40.0
