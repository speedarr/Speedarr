"""Unraid throttle start/end notifications (issue #30, optional)."""
from app.config import UnraidConfig
from app.services.unraid_monitor import UnraidStatus
from app.services.polling_monitor import PollingMonitor
from tests.conftest import make_config


class _Spy:
    def __init__(self):
        self.events = []

    async def notify(self, event_type, message, data=None):
        self.events.append(event_type)


def _pm(spy):
    cfg = make_config()
    cfg.unraid = UnraidConfig(enabled=True, url="http://tower", api_key="k",
                              download_limit_mbps=5, upload_limit_mbps=5)
    return PollingMonitor(cfg, decision_engine=None, controller_manager=None, notification_service=spy)


async def test_started_then_ended_fire_once():
    spy = _Spy()
    pm = _pm(spy)
    await pm._apply_unraid_status(UnraidStatus(True, False, False, "STARTED", 1))   # start
    await pm._apply_unraid_status(UnraidStatus(True, False, False, "STARTED", 2))   # still active (no dup)
    await pm._apply_unraid_status(UnraidStatus(False, False, False, "STARTED", None))  # end
    assert spy.events.count("unraid_throttle_started") == 1
    assert spy.events.count("unraid_throttle_ended") == 1
