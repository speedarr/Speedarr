"""Persistence for the throttling on/off toggle (issue #78)."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.database import Base
from app.models.configuration import Configuration
from app.services.throttling_state import (
    ThrottlingState,
    load_throttling_state,
    save_throttling_disabled,
    clear_throttling_state,
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


async def test_load_defaults_to_enabled_when_absent(db_session):
    state = await load_throttling_state(db_session)
    assert state == ThrottlingState(disabled=False, disabled_until=None, disabled_by=None)


async def test_save_and_load_roundtrip_with_window(db_session):
    until = datetime.now(timezone.utc) + timedelta(hours=1)
    await save_throttling_disabled(db_session, until=until, by="corey")
    await db_session.commit()
    state = await load_throttling_state(db_session)
    assert state.disabled is True
    assert state.disabled_by == "corey"
    assert abs((state.disabled_until - until).total_seconds()) < 1


async def test_save_indefinite_and_clear(db_session):
    await save_throttling_disabled(db_session, until=None, by="corey")
    await db_session.commit()
    state = await load_throttling_state(db_session)
    assert state.disabled is True and state.disabled_until is None

    await clear_throttling_state(db_session)
    await db_session.commit()
    state = await load_throttling_state(db_session)
    assert state.disabled is False and state.disabled_by is None


async def test_expired_window_loads_as_enabled(db_session):
    """Effective state is computed on read: a past window means enabled."""
    past = datetime.now(timezone.utc) - timedelta(minutes=5)
    await save_throttling_disabled(db_session, until=past, by="corey")
    await db_session.commit()
    state = await load_throttling_state(db_session)
    assert state.disabled is False


async def test_keys_are_underscore_prefixed(db_session):
    """Underscore prefix protects the rows from update_full_config deletion."""
    await save_throttling_disabled(db_session, until=None, by="corey")
    await db_session.commit()
    from sqlalchemy import select
    rows = (await db_session.execute(select(Configuration.key))).scalars().all()
    assert rows and all(k.startswith("_throttling") for k in rows)


async def test_naive_disabled_until_is_coerced_to_utc(db_session):
    """A naive ISO timestamp in storage (no tzinfo) is treated as UTC on load."""
    db_session.add(Configuration(key="_throttling_enabled", value="false", value_type="string"))
    db_session.add(
        Configuration(
            key="_throttling_disabled_until",
            value="2999-01-01T12:00:00",
            value_type="string",
        )
    )
    await db_session.commit()
    state = await load_throttling_state(db_session)
    assert state.disabled is True
    assert state.disabled_until is not None
    assert state.disabled_until.tzinfo is not None


async def test_malformed_disabled_until_fails_open(db_session):
    """A corrupted timestamp must not raise; load fails open to enabled."""
    db_session.add(Configuration(key="_throttling_enabled", value="false", value_type="string"))
    db_session.add(
        Configuration(
            key="_throttling_disabled_until",
            value="not-a-date",
            value_type="string",
        )
    )
    await db_session.commit()
    state = await load_throttling_state(db_session)
    assert state == ThrottlingState(disabled=False, disabled_until=None, disabled_by=None)


async def test_full_config_save_preserves_toggle_state(db_session):
    """update_full_config must not delete the underscore state keys."""
    from types import SimpleNamespace
    from app.services.config_manager import ConfigManager
    from tests.conftest import make_config

    # Seed: migrated sentinel + disabled toggle state
    db_session.add(Configuration(key="_migrated", value="true", value_type="boolean"))
    await save_throttling_disabled(db_session, until=None, by="corey")
    await db_session.commit()

    fake_app = SimpleNamespace(state=SimpleNamespace())
    manager = ConfigManager(fake_app)
    await manager.update_full_config(make_config().model_dump(mode="json"), db_session)

    state = await load_throttling_state(db_session)
    assert state.disabled is True and state.disabled_by == "corey"
