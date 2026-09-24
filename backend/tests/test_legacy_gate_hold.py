"""Transitional (audit T1-3 -> T1-1): rows for the four new secret keys that a pre-fix database holds
in clear must still load until the T1-1 migration encrypts them. Task 8 deletes this file; from then
on the loader is strict (tests/test_config_secrets_at_rest.py) and the startup migration
(tests/test_secrets_migration.py) is what handles a pre-fix database.

The placeholder test below is a permanent guard and moves to test_config_secrets_at_rest.py in Task 8.
"""
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


async def _row(db, key):
    return (await db.execute(select(Configuration).where(Configuration.key == key))).scalar_one_or_none()


async def _history_count(db):
    return (await db.execute(select(func.count()).select_from(ConfigurationHistory))).scalar()


async def test_clear_rows_for_the_new_keys_still_load_until_t1_1(db):
    cm = ConfigManager(app=None)
    await cm.migrate_yaml_to_db(_base(), db)
    (await _row(db, "snmp.community")).value = "AUDITMARK-snmp"            # as a pre-fix database holds it
    (await _row(db, "notifications.ntfy.topic")).value = "AUDITMARK-topic"
    await db.commit()

    loaded = await cm.load_config_from_db(db)

    assert loaded.snmp.community == "AUDITMARK-snmp"
    assert loaded.notifications.ntfy.topic == "AUDITMARK-topic"


@pytest.mark.parametrize("key", [
    "snmp.community",
    "notifications.pushover.user_key",
    "notifications.telegram.chat_id",
    "notifications.ntfy.topic",
    "plex.token",
])
async def test_placeholder_keeps_the_stored_value_and_adds_no_history(db, key):
    cm = ConfigManager(app=None)
    await cm._update_key(key, "AUDITMARK-value", db, None)
    await db.commit()
    before = (await _row(db, key)).value
    history_before = await _history_count(db)

    await cm._update_key(key, REDACTED, db, None)
    await db.commit()

    assert (await _row(db, key)).value == before
    assert await _history_count(db) == history_before
