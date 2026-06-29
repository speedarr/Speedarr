"""_reload_services rebuilds/disables the Unraid monitor (issue #30)."""
from types import SimpleNamespace

from app.config import UnraidConfig
from app.services.config_manager import ConfigManager
from app.services.polling_monitor import PollingMonitor
from app.services.unraid_monitor import UnraidMonitor
from tests.conftest import make_config


def _manager_with_pm(pm):
    app = SimpleNamespace(state=SimpleNamespace(polling_monitor=pm))
    return ConfigManager(app)


async def test_reload_builds_monitor_when_enabled():
    pm = PollingMonitor(make_config(), decision_engine=None, controller_manager=None)
    cfg = make_config()
    cfg.unraid = UnraidConfig(enabled=True, url="http://tower", api_key="k")
    await _manager_with_pm(pm)._reload_services("unraid", cfg)
    assert isinstance(pm.unraid_monitor, UnraidMonitor)


async def test_reload_disables_monitor_and_clears_override():
    pm = PollingMonitor(make_config(), decision_engine=None, controller_manager=None)
    pm.unraid_monitor = UnraidMonitor(UnraidConfig(enabled=True, url="http://tower", api_key="k"))
    pm._unraid_override = {"download_mbps": 5, "upload_mbps": 5, "reasons": ["mover"], "holding": False}
    cfg = make_config()  # unraid disabled by default
    await _manager_with_pm(pm)._reload_services("unraid", cfg)
    assert pm.unraid_monitor is None
    assert pm._unraid_override is None
