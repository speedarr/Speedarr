"""config.py and config_manager.py log through loguru (audit T4-2).

Before: both used logging.getLogger(__name__) with no bridge to loguru, so their INFO lines were
dropped and their warnings reached neither speedarr.log nor the Log Level setting.
"""
from types import SimpleNamespace

from sqlalchemy import select

from app.config import (
    SpeedarrConfig, BandwidthConfig, DownloadBandwidthConfig, UploadBandwidthConfig,
    StreamBandwidthConfig, MediaServerConfig,
)
from app.models.configuration import Configuration
from app.services.config_manager import ConfigManager


def _manager():
    state = SimpleNamespace(config=None, polling_monitor=None, decision_engine=None,
                            controller_manager=None, notification_service=None)
    return ConfigManager(app=SimpleNamespace(state=state))


def _base():
    return SpeedarrConfig(bandwidth=BandwidthConfig(
        download=DownloadBandwidthConfig(total_limit=100.0),
        upload=UploadBandwidthConfig(total_limit=50.0),
        streams=StreamBandwidthConfig(),
    ))


async def test_config_manager_warning_reaches_loguru(db, loguru_lines):
    cm = _manager()
    await cm.migrate_yaml_to_db(_base(), db)
    row = (await db.execute(select(Configuration).where(
        Configuration.key == "bandwidth.streams.overhead_percent"))).scalar_one()
    row.value, row.value_type = "500", "integer"
    await db.commit()

    await cm.clamp_stored_bounds(db)

    assert ("WARNING", "Config bandwidth.streams.overhead_percent = 500 is outside 0..300; stored 300 (audit B4-1/D1-6)") in loguru_lines


def test_config_module_warning_reaches_loguru(loguru_lines):
    MediaServerConfig(lan_networks=["not-a-network"])
    assert ("WARNING", "Ignoring invalid LAN network entry: 'not-a-network'") in loguru_lines
