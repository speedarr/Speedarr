"""Every save hands the new config to every service that keeps one (audit T3-2).

Before: _reload_services updated the decision engine on a bandwidth save and the polling monitor on
a system or snmp save only. The polling monitor reads failsafe.plex_timeout, bandwidth.streams.* and
download_reserve_percent through its own reference and the engine reads restoration.delays through
its own, so Holding Times, the Media Server Timeout and the stream overhead kept their old values
until a restart while the API reported every section as requiring none.
"""
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.config import (
    SpeedarrConfig, BandwidthConfig, DownloadBandwidthConfig, UploadBandwidthConfig,
    StreamBandwidthConfig,
)
from app.models.configuration import Configuration
from app.services.config_manager import ConfigManager


def _config(overhead=100):
    return SpeedarrConfig(bandwidth=BandwidthConfig(
        download=DownloadBandwidthConfig(total_limit=100.0),
        upload=UploadBandwidthConfig(total_limit=50.0),
        streams=StreamBandwidthConfig(overhead_percent=overhead),
    ))


def _services(old):
    """Four stand-ins holding the old config, plus the polling monitor's rebuild hooks."""
    pm = SimpleNamespace(config=old, media_servers={}, _server_state={}, snmp_monitor=None)
    return SimpleNamespace(
        config=old,
        decision_engine=SimpleNamespace(config=old),
        controller_manager=SimpleNamespace(config=old, reload_clients=AsyncMock(return_value={})),
        notification_service=SimpleNamespace(config=old),
        polling_monitor=pm,
        media_servers={},
    )


SECTIONS = ["failsafe", "restoration", "bandwidth", "history", "notifications", "system", "snmp",
            "media_servers", "plex", "qbittorrent", "sabnzbd", "transmission", "nzbget", "deluge"]


@pytest.mark.parametrize("section", SECTIONS)
async def test_every_section_save_reaches_every_service(section):
    old, new = _config(100), _config(200)
    state = _services(old)
    cm = ConfigManager(SimpleNamespace(state=state))

    await cm._reload_services(section, new)

    assert state.decision_engine.config is new, section
    assert state.controller_manager.config is new, section
    assert state.notification_service.config is new, section
    assert state.polling_monitor.config is new, section


async def test_client_sections_still_rebuild_the_clients_and_others_do_not():
    state = _services(_config())
    cm = ConfigManager(SimpleNamespace(state=state))
    new = _config(200)
    await cm._reload_services("qbittorrent", new)
    state.controller_manager.reload_clients.assert_awaited_once_with(new)
    state.controller_manager.reload_clients.reset_mock()
    await cm._reload_services("failsafe", new)
    state.controller_manager.reload_clients.assert_not_awaited()


async def test_snmp_save_still_rebuilds_or_drops_the_monitor():
    state = _services(_config())
    cm = ConfigManager(SimpleNamespace(state=state))
    await cm._reload_services("snmp", _config())        # snmp disabled by default
    assert state.polling_monitor.snmp_monitor is None


@pytest.mark.parametrize("section", SECTIONS)
async def test_setup_mode_singletons_are_skipped_without_error(section, caplog):
    state = SimpleNamespace(config=None, polling_monitor=None, decision_engine=None,
                            controller_manager=None, notification_service=None, media_servers={})
    cm = ConfigManager(SimpleNamespace(state=state))
    with caplog.at_level(logging.ERROR, logger="app.services.config_manager"):
        await cm._reload_services(section, _config())
    assert [r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR] == []


async def test_a_failing_rebuild_no_longer_leaves_a_stale_reference():
    old, new = _config(100), _config(200)
    state = _services(old)
    state.controller_manager.reload_clients = AsyncMock(side_effect=RuntimeError("boom"))
    cm = ConfigManager(SimpleNamespace(state=state))
    await cm._reload_services("qbittorrent", new)        # best-effort: logs, does not raise
    assert state.polling_monitor.config is new
    assert state.decision_engine.config is new
    assert state.notification_service.config is new


async def test_full_config_write_fans_out_too(db):
    db.add(Configuration(key="_migrated", value="true", value_type="boolean"))
    await db.commit()
    state = _services(_config(100))
    cm = ConfigManager(SimpleNamespace(state=state))
    reloaded = await cm.update_full_config(_config(200).model_dump(), db)
    assert reloaded.bandwidth.streams.overhead_percent == 200
    assert state.polling_monitor.config is reloaded
    assert state.decision_engine.config is reloaded
    assert state.notification_service.config is reloaded
    assert state.controller_manager.config is reloaded
