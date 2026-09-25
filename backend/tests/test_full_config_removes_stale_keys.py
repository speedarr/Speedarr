"""A full-config write removes rows for keys that are no longer in the config (audit NEW-1).

Before: the stale-key select used `key.startswith("_")` with SQLAlchemy's default autoescape=False,
where `_` is a LIKE single-character wildcard, so the negated match selected no row and the removal
step had never removed anything. Both callers pass a full model dump, so the removal only ever drops
rows whose keys are no longer model fields.
"""
from types import SimpleNamespace

from sqlalchemy import select

from app.config import (
    SpeedarrConfig, BandwidthConfig, DownloadBandwidthConfig, UploadBandwidthConfig,
    StreamBandwidthConfig,
)
from app.models.configuration import Configuration
from app.services.config_manager import ConfigManager


def _base():
    return SpeedarrConfig(bandwidth=BandwidthConfig(
        download=DownloadBandwidthConfig(total_limit=100.0),
        upload=UploadBandwidthConfig(total_limit=50.0),
        streams=StreamBandwidthConfig(),
    ))


def _manager():
    return ConfigManager(SimpleNamespace(state=SimpleNamespace(
        config=None, polling_monitor=None, decision_engine=None,
        controller_manager=None, notification_service=None)))


async def _keys(db):
    return {r.key for r in (await db.execute(select(Configuration))).scalars().all()}


async def test_full_config_write_removes_stale_rows_and_keeps_internal_ones(db):
    cm = _manager()
    await cm.migrate_yaml_to_db(_base(), db)
    db.add(Configuration(key="legacy.section.key", value="1", value_type="integer"))
    db.add(Configuration(key="_throttling_state", value="{}", value_type="json"))
    await db.commit()

    await cm.update_full_config(_base().model_dump(), db)

    keys = await _keys(db)
    assert "legacy.section.key" not in keys
    assert "_throttling_state" in keys and "_migrated" in keys
    assert "bandwidth.download.total_limit" in keys
