"""Server-side bounds on four settings and the startup heal pass (audit B4-1, D1-6).

Before: inactive_safety_net_percent, overhead_percent, download_reserve_percent and update_frequency
had no upper bound in the model, so a mistyped value reached the engine and the poll loops. A bound
alone would make an existing database with such a value fail to load and start the app in setup
mode, so clamp_stored_bounds pulls stored rows back inside the bounds at startup, before the loader.
"""
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.config import (
    SpeedarrConfig, BandwidthConfig, DownloadBandwidthConfig, UploadBandwidthConfig,
    StreamBandwidthConfig, SystemConfig,
)
from app.models.configuration import Configuration, ConfigurationHistory
from app.services.config_manager import ConfigManager, bounded_scalar_keys


def _base():
    return SpeedarrConfig(bandwidth=BandwidthConfig(
        download=DownloadBandwidthConfig(total_limit=100.0),
        upload=UploadBandwidthConfig(total_limit=50.0),
        streams=StreamBandwidthConfig(),
    ))


def _manager():
    state = SimpleNamespace(config=None, polling_monitor=None, decision_engine=None,
                            controller_manager=None, notification_service=None)
    return ConfigManager(app=SimpleNamespace(state=state))


async def _row(db, key):
    return (await db.execute(select(Configuration).where(Configuration.key == key))).scalar_one_or_none()


async def _seed(db, key, value, value_type):
    """Write a row the way an older writer might have: value and type given verbatim."""
    row = await _row(db, key)
    if row is None:
        db.add(Configuration(key=key, value=str(value), value_type=value_type))
    else:
        row.value, row.value_type = str(value), value_type
    await db.commit()


# --- the model refuses out-of-range values ---------------------------------------------------

@pytest.mark.parametrize("value", [-1, 21, 150])
def test_safety_net_percent_is_bounded_0_to_20(value):
    with pytest.raises(ValidationError):
        DownloadBandwidthConfig(total_limit=100.0, inactive_safety_net_percent=value)
    assert DownloadBandwidthConfig(total_limit=100.0, inactive_safety_net_percent=20).inactive_safety_net_percent == 20
    assert DownloadBandwidthConfig(total_limit=100.0, inactive_safety_net_percent=0).inactive_safety_net_percent == 0


@pytest.mark.parametrize("value", [-1, 301])
def test_overhead_percent_is_bounded_0_to_300(value):
    with pytest.raises(ValidationError):
        StreamBandwidthConfig(overhead_percent=value)
    assert StreamBandwidthConfig(overhead_percent=300).overhead_percent == 300


@pytest.mark.parametrize("value", [-1, 101])
def test_download_reserve_percent_is_bounded_0_to_100(value):
    with pytest.raises(ValidationError):
        StreamBandwidthConfig(download_reserve_percent=value)
    assert StreamBandwidthConfig(download_reserve_percent=100).download_reserve_percent == 100


# --- the walk finds every bounded scalar key ---------------------------------------------------

def test_bounded_scalar_keys_cover_the_bandwidth_fields_and_skip_list_sections():
    keys = bounded_scalar_keys()
    assert keys["bandwidth.download.inactive_safety_net_percent"] == (0, 20, False)
    assert keys["bandwidth.streams.overhead_percent"] == (0, 300, False)
    assert keys["bandwidth.streams.download_reserve_percent"] == (0, 100, False)
    assert keys["history.retention_days"] == (1, 90, False)
    assert keys["bandwidth.download.min_limit_mbps"] == (0, None, False)
    assert not any(k.startswith(("media_servers", "download_clients")) for k in keys)


def test_the_model_has_no_strict_bound_the_heal_pass_would_skip():
    # clamp_stored_bounds honours inclusive ge/le only. Adding a gt/lt bound anywhere in the config
    # model without extending it makes this fail loudly instead of leaving a silent gap.
    assert [k for k, (_, _, strict) in bounded_scalar_keys().items() if strict] == []


# --- the heal pass -----------------------------------------------------------------------------

async def test_clamp_pulls_stored_rows_to_the_bound_and_records_history(db, caplog):
    cm = _manager()
    await cm.migrate_yaml_to_db(_base(), db)                       # writes _migrated and every key
    await _seed(db, "bandwidth.download.inactive_safety_net_percent", 150, "integer")
    await _seed(db, "bandwidth.streams.overhead_percent", 500, "integer")
    await _seed(db, "bandwidth.streams.download_reserve_percent", 20, "integer")   # in range

    with caplog.at_level(logging.WARNING, logger="app.services.config_manager"):
        clamped = await cm.clamp_stored_bounds(db)

    assert clamped == 2
    assert (await _row(db, "bandwidth.download.inactive_safety_net_percent")).value == "20"
    assert (await _row(db, "bandwidth.streams.overhead_percent")).value == "300"
    assert (await _row(db, "bandwidth.streams.download_reserve_percent")).value == "20"
    history = (await db.execute(select(ConfigurationHistory).where(
        ConfigurationHistory.key == "bandwidth.download.inactive_safety_net_percent"
    ).order_by(ConfigurationHistory.id))).scalars().all()
    assert history[-1].old_value == "150" and history[-1].new_value == "20"
    messages = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert any("inactive_safety_net_percent = 150 is outside 0..20; stored 20" in m for m in messages)
    assert any("overhead_percent = 500 is outside 0..300; stored 300" in m for m in messages)
    assert not any("download_reserve_percent" in m for m in messages)
    loaded = await cm.load_config_from_db(db)
    assert loaded.bandwidth.download.inactive_safety_net_percent == 20
    assert loaded.bandwidth.streams.overhead_percent == 300


async def test_clamp_heals_an_int_field_stored_with_float_type(db):
    # Review Focus 2: an older writer stored "150.0" under value_type float.
    cm = _manager()
    await cm.migrate_yaml_to_db(_base(), db)
    await _seed(db, "bandwidth.download.inactive_safety_net_percent", "150.0", "float")
    assert await cm.clamp_stored_bounds(db) == 1
    assert (await cm.load_config_from_db(db)).bandwidth.download.inactive_safety_net_percent == 20


async def test_clamp_is_idempotent_and_leaves_in_range_rows_untouched(db):
    cm = _manager()
    await cm.migrate_yaml_to_db(_base(), db)
    before = {r.key: r.value for r in (await db.execute(select(Configuration))).scalars().all()}
    assert await cm.clamp_stored_bounds(db) == 0
    assert await cm.clamp_stored_bounds(db) == 0
    after = {r.key: r.value for r in (await db.execute(select(Configuration))).scalars().all()}
    assert after == before


async def test_clamp_is_a_noop_before_migration(db):
    assert await _manager().clamp_stored_bounds(db) == 0
    assert (await db.execute(select(Configuration))).scalars().all() == []


async def test_clamp_skips_a_non_numeric_row(db):
    cm = _manager()
    await cm.migrate_yaml_to_db(_base(), db)
    await _seed(db, "bandwidth.streams.overhead_percent", "lots", "string")
    assert await cm.clamp_stored_bounds(db) == 0
    assert (await _row(db, "bandwidth.streams.overhead_percent")).value == "lots"


async def test_saving_an_out_of_range_safety_net_is_refused_and_nothing_is_written(db):
    cm = _manager()
    await cm.migrate_yaml_to_db(_base(), db)
    cm.app.state.config = await cm.load_config_from_db(db)
    cm._reload_services = AsyncMock()
    with pytest.raises(ValueError, match="bandwidth.download.inactive_safety_net_percent"):
        await cm.update_section("bandwidth", {"download": {"inactive_safety_net_percent": 150}}, db)
    assert (await _row(db, "bandwidth.download.inactive_safety_net_percent")).value == "5"


# --- polling interval (audit D1-6) -------------------------------------------------------------

@pytest.mark.parametrize("value", [4, 301, 10**12])
def test_update_frequency_is_bounded_5_to_300(value):
    with pytest.raises(ValidationError):
        SystemConfig(update_frequency=value)
    assert SystemConfig(update_frequency=300).update_frequency == 300
    assert bounded_scalar_keys()["system.update_frequency"] == (5, 300, False)


async def test_clamp_pulls_a_huge_stored_polling_interval_back_to_300(db):
    cm = _manager()
    await cm.migrate_yaml_to_db(_base(), db)
    await _seed(db, "system.update_frequency", 10**12, "integer")      # the audit sweep's value
    assert await cm.clamp_stored_bounds(db) == 1
    assert (await _row(db, "system.update_frequency")).value == "300"
    assert (await cm.load_config_from_db(db)).system.update_frequency == 300


async def test_clamp_pulls_a_stored_polling_interval_below_the_floor_up_to_5(db):
    # Review Focus 1: healing works upward too.
    cm = _manager()
    await cm.migrate_yaml_to_db(_base(), db)
    await _seed(db, "system.update_frequency", 1, "integer")
    assert await cm.clamp_stored_bounds(db) == 1
    assert (await cm.load_config_from_db(db)).system.update_frequency == 5


async def test_saving_an_oversized_polling_interval_is_refused_and_nothing_is_written(db):
    cm = _manager()
    await cm.migrate_yaml_to_db(_base(), db)
    cm.app.state.config = await cm.load_config_from_db(db)
    cm._reload_services = AsyncMock()
    with pytest.raises(ValueError, match="system.update_frequency"):
        await cm.update_section("system", {"update_frequency": 5000}, db)
    assert (await _row(db, "system.update_frequency")).value == "5"
