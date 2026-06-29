"""Settings test-connection branch for Unraid (issue #30)."""
from types import SimpleNamespace
from unittest.mock import patch

from app.api import settings
from app.config import UnraidConfig
from tests.conftest import make_config


def _request(config):
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(config=config)))


class _FakeMonitor:
    def __init__(self, cfg):
        self.cfg = cfg

    async def test_connection(self):
        return True, "Connected. Array STARTED, parity idle, mover idle."


async def test_unraid_test_connection_success():
    req = _request(make_config())
    tr = settings.TestConnectionRequest(config={"url": "http://tower", "api_key": "k"}, use_existing=False)
    with patch("app.services.unraid_monitor.UnraidMonitor", _FakeMonitor):
        resp = await settings.test_connection("unraid", tr, req, current_user=None)
    assert resp.success is True
    assert "Array STARTED" in resp.message


async def test_unraid_test_connection_missing_fields():
    req = _request(make_config())
    tr = settings.TestConnectionRequest(config={"url": "http://tower"}, use_existing=False)  # no api_key
    resp = await settings.test_connection("unraid", tr, req, current_user=None)
    assert resp.success is False
    assert "api_key" in resp.message.lower() or "required" in resp.message.lower()


async def test_unraid_test_connection_reuses_saved_key_when_masked():
    cfg = make_config()
    cfg.unraid = UnraidConfig(enabled=True, url="http://tower", api_key="saved-secret")
    req = _request(cfg)
    tr = settings.TestConnectionRequest(config={"url": "http://tower", "api_key": "***REDACTED***"}, use_existing=False)
    captured = {}

    class _Capture(_FakeMonitor):
        def __init__(self, c):
            captured["api_key"] = c.api_key

    with patch("app.services.unraid_monitor.UnraidMonitor", _Capture):
        resp = await settings.test_connection("unraid", tr, req, current_user=None)
    assert captured["api_key"] == "saved-secret"
    assert resp.success is True
