"""The temporary-limit endpoints persist before they touch memory (issue #108)."""
import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool

import app.api.bandwidth as bandwidth_api
from app.api.bandwidth import (
    TemporaryLimitRequest,
    set_temporary_limits,
    clear_temporary_limits,
    get_temporary_limits,
)
from app.database import Base
from app.services.temporary_limits_state import load_temporary_limits


@pytest.fixture
async def maker(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(bandwidth_api, "AsyncSessionLocal", maker)
    yield maker
    await engine.dispose()


def _request(api_key_name=None):
    pm = SimpleNamespace(_temporary_limits=None, _temporary_limits_lock=asyncio.Lock())
    state = SimpleNamespace()
    if api_key_name:
        state.api_key_name = api_key_name
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(polling_monitor=pm)), state=state)


def _user():
    return SimpleNamespace(username="admin")


async def _stored(maker):
    async with maker() as db:
        return await load_temporary_limits(db)


async def test_set_persists_timed_limit(maker):
    request = _request()
    body = TemporaryLimitRequest(download_mbps=50, upload_mbps=10, duration_hours=2, source="Gaming PC")
    response = await set_temporary_limits(request, body, _user())
    assert response.active is True and response.set_by == "admin"

    stored = await _stored(maker)
    assert stored["download_mbps"] == 50 and stored["upload_mbps"] == 10
    assert stored["set_by"] == "admin" and stored["source"] == "Gaming PC"
    assert stored["expires_at"] > datetime.now(timezone.utc)

    pm = request.app.state.polling_monitor
    assert pm._temporary_limits["download_mbps"] == 50
    assert pm._temporary_limits["expires_at"] == stored["expires_at"]


async def test_set_persists_indefinite_limit_from_api_key(maker):
    request = _request(api_key_name="Unraid")
    body = TemporaryLimitRequest(download_mbps=20, upload_mbps=None)
    await set_temporary_limits(request, body, _user())
    stored = await _stored(maker)
    assert stored["expires_at"] is None
    assert stored["upload_mbps"] is None
    assert stored["set_by"] == "API: Unraid"
    assert request.app.state.polling_monitor._temporary_limits["set_by"] == "API: Unraid"


async def test_clear_removes_row_and_memory(maker):
    request = _request()
    await set_temporary_limits(request, TemporaryLimitRequest(download_mbps=50), _user())
    assert await _stored(maker) is not None

    result = await clear_temporary_limits(request, _user())
    assert result["active"] is False
    assert await _stored(maker) is None
    assert request.app.state.polling_monitor._temporary_limits is None
    assert (await get_temporary_limits(request)).active is False


async def test_clear_when_nothing_set_is_fine(maker):
    request = _request()
    result = await clear_temporary_limits(request, _user())
    assert result["active"] is False
    assert await _stored(maker) is None
