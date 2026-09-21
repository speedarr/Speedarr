"""Regression tests for #32: media-servers PUT during the setup wizard.

In setup mode main.py sets app.state.polling_monitor (and the other service
singletons) to None rather than leaving them unset. The PUT handler's
connection-test loop and ConfigManager._reload_services both guarded with
hasattr, which is True for a None-valued attribute, and then dereferenced None.
The handler's deref escaped as a 500 that aborted the wizard before
complete-setup could run; the reload path's were swallowed but logged as ERROR.

  1. update_media_servers must return normally (empty connection_results)
     when polling_monitor is None.
  2. _reload_services must skip cleanly (no ERROR log) for every section
     when the service singletons are None.
"""
import logging
from types import SimpleNamespace

import pytest

from app.api.settings import MediaServersUpdateRequest, update_media_servers
from app.config import (
    SpeedarrConfig,
    BandwidthConfig,
    DownloadBandwidthConfig,
    UploadBandwidthConfig,
    StreamBandwidthConfig,
)
from app.services.config_manager import ConfigManager


def _config():
    return SpeedarrConfig(
        bandwidth=BandwidthConfig(
            download=DownloadBandwidthConfig(total_limit=100.0, min_limit_mbps=1.0),
            upload=UploadBandwidthConfig(total_limit=50.0, min_limit_mbps=1.0),
            streams=StreamBandwidthConfig(),
        )
    )


def _setup_mode_state(config_manager):
    """Mirror main.py's setup-mode app.state: service attributes present but None."""
    return SimpleNamespace(
        config=None,
        polling_monitor=None,
        decision_engine=None,
        controller_manager=None,
        notification_service=None,
        media_servers={},
        config_manager=config_manager,
    )


class _SetupModeConfigManager:
    """Stands in for the DB-backed ConfigManager; no database in these tests."""

    def __init__(self):
        self.reloaded = []

    async def load_config_from_db(self, db):
        return _config()

    async def update_full_config(self, config_data, db, user_id=None):
        return SpeedarrConfig(**config_data)

    async def _reload_services(self, section_name, config):
        self.reloaded.append(section_name)


JELLYFIN = {
    "name": "Jellyfin",
    "type": "jellyfin",
    "url": "http://jellyfin:8096",
    "api_key": "abc123",
}


@pytest.mark.asyncio
async def test_update_media_servers_in_setup_mode_skips_connection_test():
    cm = _SetupModeConfigManager()
    request = SimpleNamespace(app=SimpleNamespace(state=_setup_mode_state(cm)))

    resp = await update_media_servers(
        MediaServersUpdateRequest(servers=[dict(JELLYFIN)]),
        request=request,
        db=None,
        current_user=SimpleNamespace(id=1),
    )

    assert [s["type"] for s in resp.servers] == ["jellyfin"]
    assert resp.connection_results == {}
    assert cm.reloaded == ["media_servers"]


@pytest.mark.parametrize(
    "section",
    ["media_servers", "plex", "qbittorrent", "bandwidth", "notifications", "system", "snmp"],
)
@pytest.mark.asyncio
async def test_reload_services_skips_none_services_without_error(section, caplog):
    app = SimpleNamespace(state=_setup_mode_state(config_manager=None))
    cm = ConfigManager(app)

    # config_manager logs via stdlib logging (not loguru), so use caplog.
    with caplog.at_level(logging.ERROR, logger="app.services.config_manager"):
        await cm._reload_services(section, _config())

    assert [r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR] == []
