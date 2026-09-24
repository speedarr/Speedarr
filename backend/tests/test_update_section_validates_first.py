"""update_section validates before it writes and commits only after a successful reload (audit T2-1).

Before: the raw dict was flattened, written and committed, and only then reloaded; a rejected value
stayed in the database and put the next boot into setup mode with no throttling.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select, func

from app.models.configuration import Configuration, ConfigurationHistory
from app.services.config_manager import ConfigManager
from app.config import (
    SpeedarrConfig, BandwidthConfig, DownloadBandwidthConfig, UploadBandwidthConfig,
    StreamBandwidthConfig, REDACTED,
)


def _base():
    return SpeedarrConfig(bandwidth=BandwidthConfig(
        download=DownloadBandwidthConfig(total_limit=100.0),
        upload=UploadBandwidthConfig(total_limit=50.0),
        streams=StreamBandwidthConfig(),
    ))


@pytest.fixture
async def cm(db):
    state = SimpleNamespace(config=None, polling_monitor=None, decision_engine=None,
                            controller_manager=None, notification_service=None)
    manager = ConfigManager(app=SimpleNamespace(state=state))
    await manager.migrate_yaml_to_db(_base(), db)
    state.config = await manager.load_config_from_db(db)
    manager._reload_services = AsyncMock()
    return manager


async def _value(db, key):
    row = (await db.execute(select(Configuration).where(Configuration.key == key))).scalar_one_or_none()
    return None if row is None else row.value


async def _rows(db):
    return {r.key: r.value for r in (await db.execute(select(Configuration))).scalars().all()}


async def _history_count(db):
    return (await db.execute(select(func.count()).select_from(ConfigurationHistory))).scalar()


async def test_invalid_value_names_the_field_and_writes_nothing(cm, db):
    before = await _rows(db)
    with pytest.raises(ValueError) as exc:
        await cm.update_section("system", {"update_frequency": 4}, db)
    assert "system.update_frequency" in str(exc.value)
    assert await _rows(db) == before
    assert await cm.load_config_from_db(db) is not None


async def test_valid_value_is_written_and_reloaded(cm, db):
    cfg = await cm.update_section("system", {"update_frequency": 10}, db)
    assert cfg.system.update_frequency == 10
    assert await _value(db, "system.update_frequency") == "10"
    assert cm.app.state.config is cfg


async def test_unknown_keys_are_dropped_even_when_nested(cm, db):
    await cm.update_section("system", {"update_frequency": 7, "audit_unknown_field": "x"}, db)
    await cm.update_section("notifications", {"pushover": {"enabled": False, "bogus": "y"}}, db)
    rows = await _rows(db)
    assert "system.audit_unknown_field" not in rows
    assert "notifications.pushover.bogus" not in rows
    assert rows["system.update_frequency"] == "7"


async def test_partial_payload_merges_with_the_current_section(cm, db):
    await cm.update_section("system", {"update_frequency": 12}, db)
    cfg = await cm.update_section("system", {"log_level": "DEBUG"}, db)
    assert cfg.system.update_frequency == 12
    assert cfg.system.log_level.upper() == "DEBUG"


async def test_placeholder_keeps_the_stored_secret_row_and_adds_no_history(cm, db):
    await cm.update_section("snmp", {"community": "AUDITMARK-snmp"}, db)
    before = await _value(db, "snmp.community")
    count = await _history_count(db)
    cfg = await cm.update_section("snmp", {"community": REDACTED, "host": "router"}, db)
    assert await _value(db, "snmp.community") == before
    assert cfg.snmp.community == "AUDITMARK-snmp" and cfg.snmp.host == "router"
    assert await _history_count(db) == count + 1        # only snmp.host


async def test_placeholder_with_nothing_stored_is_skipped_not_stored(cm, db):
    # Fresh install: the UI posts the placeholder for an empty chat id; the row must not become the literal.
    cfg = await cm.update_section("notifications", {"telegram": {"chat_id": REDACTED}}, db)
    assert await _value(db, "notifications.telegram.chat_id") == "None"   # the wizard's default row, untouched
    assert cfg.notifications.telegram.chat_id is None


async def test_null_on_a_required_field_is_refused(cm, db):
    with pytest.raises(ValueError, match="system.update_frequency"):
        await cm.update_section("system", {"update_frequency": None}, db)


async def test_null_on_an_optional_field_deletes_the_row(cm, db):
    await cm.update_section("notifications", {"stream_count_threshold": 3}, db)
    assert await _value(db, "notifications.stream_count_threshold") == "3"
    cfg = await cm.update_section("notifications", {"stream_count_threshold": None}, db)
    assert await _value(db, "notifications.stream_count_threshold") is None
    assert cfg.notifications.stream_count_threshold is None


async def test_reload_failure_rolls_back(cm, db, monkeypatch):
    before = await _rows(db)
    monkeypatch.setattr(cm, "load_config_from_db", AsyncMock(return_value=None))
    with pytest.raises(ValueError, match="nothing was written"):
        await cm.update_section("system", {"update_frequency": 30}, db)
    monkeypatch.undo()
    assert await _rows(db) == before


async def test_partial_put_to_the_unset_legacy_section_is_refused(cm, db):
    # The audit's damaging case: rows for a half-configured qbittorrent section broke every later save.
    before = await _rows(db)
    with pytest.raises(ValueError, match="qbittorrent"):
        await cm.update_section("qbittorrent", {"enabled": True}, db)
    assert await _rows(db) == before


async def test_list_section_is_refused_with_the_endpoint_name(cm, db):
    with pytest.raises(ValueError, match="/api/settings/download-clients"):
        await cm.update_section("download_clients", [{"id": "x"}], db)


async def test_unknown_section_is_refused(cm, db):
    with pytest.raises(ValueError, match="Unknown section"):
        await cm.update_section("nope", {"a": 1}, db)


async def test_full_config_reload_failure_rolls_back(cm, db, monkeypatch):
    before = await _rows(db)
    data = _base().model_dump()
    data["system"]["update_frequency"] = 42
    monkeypatch.setattr(cm, "load_config_from_db", AsyncMock(return_value=None))
    with pytest.raises(ValueError, match="nothing was written"):
        await cm.update_full_config(data, db)
    monkeypatch.undo()
    assert await _rows(db) == before
