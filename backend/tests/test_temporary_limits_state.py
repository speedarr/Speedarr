"""Persistence for temporary bandwidth limits (issue #108)."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.database import Base
from app.models.configuration import Configuration
from app.services.temporary_limits_state import (
    KEY,
    load_temporary_limits,
    save_temporary_limits,
    clear_temporary_limits,
)


@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


def _limits(expires_at, set_at=None):
    return {
        "download_mbps": 50.0,
        "upload_mbps": 10.0,
        "expires_at": expires_at,
        "set_by": "corey",
        "set_at": set_at or datetime.now(timezone.utc),
        "source": "Home Assistant - Gaming PC",
    }


async def test_load_absent_is_none(db_session):
    assert await load_temporary_limits(db_session) is None


async def test_save_and_load_roundtrip_with_expiry(db_session):
    until = datetime.now(timezone.utc) + timedelta(hours=2)
    await save_temporary_limits(db_session, _limits(until))
    await db_session.commit()
    loaded = await load_temporary_limits(db_session)
    assert loaded["download_mbps"] == 50.0
    assert loaded["upload_mbps"] == 10.0
    assert loaded["set_by"] == "corey"
    assert loaded["source"] == "Home Assistant - Gaming PC"
    assert loaded["expires_at"].tzinfo is not None
    assert abs((loaded["expires_at"] - until).total_seconds()) < 1
    assert isinstance(loaded["set_at"], datetime) and loaded["set_at"].tzinfo is not None


async def test_indefinite_roundtrip_and_clear(db_session):
    await save_temporary_limits(db_session, _limits(None))
    await db_session.commit()
    loaded = await load_temporary_limits(db_session)
    assert loaded is not None and loaded["expires_at"] is None

    await clear_temporary_limits(db_session)
    await db_session.commit()
    assert await load_temporary_limits(db_session) is None


async def test_only_one_direction_survives_as_none(db_session):
    limits = _limits(None)
    limits["upload_mbps"] = None
    await save_temporary_limits(db_session, limits)
    await db_session.commit()
    loaded = await load_temporary_limits(db_session)
    assert loaded["download_mbps"] == 50.0 and loaded["upload_mbps"] is None


async def test_save_replaces_previous_row(db_session):
    await save_temporary_limits(db_session, _limits(None))
    await db_session.commit()
    second = _limits(None)
    second["download_mbps"] = 5.0
    await save_temporary_limits(db_session, second)
    await db_session.commit()
    rows = (await db_session.execute(select(Configuration).where(Configuration.key == KEY))).scalars().all()
    assert len(rows) == 1
    assert (await load_temporary_limits(db_session))["download_mbps"] == 5.0


async def test_expired_row_loads_as_none(db_session):
    """Effective state is computed on read: a past expiry means no limit."""
    past = datetime.now(timezone.utc) - timedelta(minutes=5)
    await save_temporary_limits(db_session, _limits(past))
    await db_session.commit()
    assert await load_temporary_limits(db_session) is None


async def test_naive_expires_at_is_coerced_to_utc(db_session):
    db_session.add(Configuration(
        key=KEY,
        value='{"download_mbps": 50, "upload_mbps": 10, "expires_at": "2999-01-01T12:00:00", '
              '"set_by": "corey", "set_at": null, "source": null}',
        value_type="json",
    ))
    await db_session.commit()
    loaded = await load_temporary_limits(db_session)
    assert loaded is not None
    assert loaded["expires_at"].tzinfo is not None


async def test_malformed_json_fails_open(db_session):
    db_session.add(Configuration(key=KEY, value="{not json", value_type="json"))
    await db_session.commit()
    assert await load_temporary_limits(db_session) is None


async def test_malformed_expires_at_fails_open(db_session):
    db_session.add(Configuration(
        key=KEY,
        value='{"download_mbps": 50, "upload_mbps": 10, "expires_at": "not-a-date"}',
        value_type="json",
    ))
    await db_session.commit()
    assert await load_temporary_limits(db_session) is None


async def test_non_object_payload_fails_open(db_session):
    db_session.add(Configuration(key=KEY, value='[1, 2, 3]', value_type="json"))
    await db_session.commit()
    assert await load_temporary_limits(db_session) is None


async def test_key_is_underscore_prefixed(db_session):
    """Underscore prefix keeps the row out of load_config_from_db and update_full_config."""
    await save_temporary_limits(db_session, _limits(None))
    await db_session.commit()
    rows = (await db_session.execute(select(Configuration.key))).scalars().all()
    assert rows == [KEY] and KEY.startswith("_")


async def test_full_config_save_preserves_temporary_limits(db_session):
    """update_full_config must not delete the underscore state key."""
    from types import SimpleNamespace
    from app.services.config_manager import ConfigManager
    from tests.conftest import make_config

    db_session.add(Configuration(key="_migrated", value="true", value_type="boolean"))
    await save_temporary_limits(db_session, _limits(None))
    await db_session.commit()

    fake_app = SimpleNamespace(state=SimpleNamespace())
    manager = ConfigManager(fake_app)
    await manager.update_full_config(make_config().model_dump(mode="json"), db_session)

    loaded = await load_temporary_limits(db_session)
    assert loaded is not None and loaded["set_by"] == "corey"
