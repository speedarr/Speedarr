"""GET /temporary-limits merges the Unraid override (issue #30)."""
from types import SimpleNamespace

from app.api import bandwidth
from app.services.polling_monitor import PollingMonitor
from tests.conftest import make_config


def _request(pm):
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(polling_monitor=pm)))


async def test_reports_unraid_override_when_only_override_active():
    pm = PollingMonitor(make_config(), decision_engine=None, controller_manager=None)
    pm._unraid_override = {"download_mbps": 5, "upload_mbps": 5, "reasons": ["parity_check"], "holding": False}
    resp = await bandwidth.get_temporary_limits(_request(pm))
    assert resp.active is True
    assert resp.download_mbps == 5 and resp.upload_mbps == 5
    assert "unraid:parity_check" in resp.source


async def test_combines_manual_and_unraid_by_min():
    pm = PollingMonitor(make_config(), decision_engine=None, controller_manager=None)
    pm._temporary_limits = {"download_mbps": 20, "upload_mbps": 2, "expires_at": None, "source": "Manual"}
    pm._unraid_override = {"download_mbps": 5, "upload_mbps": 5, "reasons": ["mover"], "holding": False}
    resp = await bandwidth.get_temporary_limits(_request(pm))
    assert resp.active is True
    assert resp.download_mbps == 5   # min(20, 5)
    assert resp.upload_mbps == 2     # min(2, 5)


async def test_inactive_when_nothing_set():
    pm = PollingMonitor(make_config(), decision_engine=None, controller_manager=None)
    resp = await bandwidth.get_temporary_limits(_request(pm))
    assert resp.active is False
