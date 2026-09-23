"""Settings › General › Log Level drives both loguru sinks (#103).

The dropdown saved system.log_level but nothing read it: the console sink was
DEBUG or INFO from the DEBUG environment variable and the file sink was fixed
at INFO. Now both sinks share one runtime threshold, applied at startup and on
every save of the system section. DEBUG=true in the environment still forces
DEBUG whatever the setting says.
"""
from types import SimpleNamespace

import pytest
from loguru import logger
from pydantic import ValidationError

from app.config import (
    SpeedarrConfig,
    SystemConfig,
    BandwidthConfig,
    DownloadBandwidthConfig,
    UploadBandwidthConfig,
    StreamBandwidthConfig,
    settings,
)
from app.utils import logger as logmod


@pytest.fixture
def log_file(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "debug", False)
    logmod.setup_logger(log_dir=tmp_path)
    logmod.set_log_level("INFO")
    yield tmp_path / "speedarr.log"
    logger.remove()


def _text(path):
    return path.read_text() if path.exists() else ""


def test_warning_hides_info_and_shows_warning(log_file):
    logmod.set_log_level("WARNING")
    logger.info("hidden-info")
    logger.warning("shown-warning")
    assert "hidden-info" not in _text(log_file)
    assert "shown-warning" in _text(log_file)


def test_debug_shows_debug_records_once_selected(log_file):
    logger.debug("hidden-before")
    logmod.set_log_level("DEBUG")
    logger.debug("shown-after")
    assert "hidden-before" not in _text(log_file)
    assert "shown-after" in _text(log_file)


def test_debug_env_wins_over_the_setting(log_file, monkeypatch):
    monkeypatch.setattr(settings, "debug", True)
    assert logmod.set_log_level("ERROR") == "DEBUG"
    assert logmod.current_log_level() == "DEBUG"
    logger.debug("env-forced-debug")
    assert "env-forced-debug" in _text(log_file)


def test_setting_accepts_the_five_names_in_any_case():
    assert SystemConfig(log_level="info").log_level == "INFO"
    assert SystemConfig(log_level="Warning").log_level == "WARNING"
    assert SystemConfig().log_level == "INFO"


def test_setting_rejects_unknown_names():
    with pytest.raises(ValidationError):
        SystemConfig(log_level="verbose")
    with pytest.raises(ValueError):
        logmod.set_log_level("verbose")


def _config(level: str) -> SpeedarrConfig:
    return SpeedarrConfig(
        bandwidth=BandwidthConfig(
            download=DownloadBandwidthConfig(total_limit=100.0, min_limit_mbps=1.0),
            upload=UploadBandwidthConfig(total_limit=50.0, min_limit_mbps=1.0),
            streams=StreamBandwidthConfig(),
        ),
        system=SystemConfig(log_level=level),
    )


@pytest.mark.asyncio
async def test_saving_the_system_section_applies_the_level(log_file):
    from app.services.config_manager import ConfigManager

    # Setup mode: the polling monitor singleton is None, not unset.
    app = SimpleNamespace(state=SimpleNamespace(polling_monitor=None))
    await ConfigManager(app)._reload_services("system", _config("ERROR"))
    assert logmod.current_log_level() == "ERROR"
    logger.warning("hidden-warning")
    assert "hidden-warning" not in _text(log_file)
