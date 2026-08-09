"""remove_all_limits + apply_decisions abort gate (issue #78)."""
import asyncio
from unittest.mock import AsyncMock

import pytest

from app.services.controller_manager import ControllerManager
from app.clients.base import BaseDownloadClient
from app.clients.sabnzbd import SABnzbdClient


class FakeClient:
    def __init__(self):
        self.calls = []
        self.unlimited_calls = 0

    async def set_speed_limits(self, download_limit=None, upload_limit=None):
        self.calls.append((download_limit, upload_limit))

    async def set_unlimited(self):
        self.unlimited_calls += 1


class FailingClient(FakeClient):
    async def set_unlimited(self):
        raise ConnectionError("down")


def _manager(clients):
    cm = ControllerManager.__new__(ControllerManager)   # bypass __init__/config
    cm.clients = clients
    cm._write_lock = asyncio.Lock()
    return cm


async def test_remove_all_limits_sets_unlimited_on_every_client():
    a, b = FakeClient(), FakeClient()
    cm = _manager({"qbittorrent_1": a, "deluge_1": b})
    results = await cm.remove_all_limits()
    assert results == {"qbittorrent_1": True, "deluge_1": True}
    assert a.unlimited_calls == 1 and b.unlimited_calls == 1


async def test_remove_all_limits_reports_failure_after_retries():
    cm = _manager({"nzbget_1": FailingClient()})
    results = await cm.remove_all_limits(retries=2, retry_delay=0)
    assert results == {"nzbget_1": False}


async def test_remove_all_limits_empty_clients():
    cm = _manager({})
    assert await cm.remove_all_limits() == {}


async def test_apply_decisions_aborts_when_gate_trips():
    a = FakeClient()
    cm = _manager({"qbittorrent_1": a})
    result = await cm.apply_decisions(
        {"qbittorrent_1": {"action": "throttle", "download_limit": 50, "upload_limit": 10, "reason": "t"}},
        abort_if=lambda: True,
    )
    assert result == {}
    assert a.calls == []


async def test_apply_decisions_proceeds_when_gate_clear():
    a = FakeClient()
    cm = _manager({"qbittorrent_1": a})
    await cm.apply_decisions(
        {"qbittorrent_1": {"action": "throttle", "download_limit": 50, "upload_limit": 10, "reason": "t"}},
        abort_if=lambda: False,
    )
    assert a.calls != []


# --- Adapter-level set_unlimited mapping (issue #78 Change 1b follow-up) ---

class _MinimalClient(BaseDownloadClient):
    """Minimal concrete subclass exercising BaseDownloadClient's default set_unlimited."""

    def __init__(self):
        super().__init__("id1", "Minimal", "http://example.test")
        self.calls = []

    async def test_connection(self):
        return True

    async def get_stats(self):
        return {}

    async def get_speed_limits(self):
        return {"download_limit": 0, "upload_limit": 0}

    async def set_speed_limits(self, download_limit=None, upload_limit=None):
        self.calls.append((download_limit, upload_limit))

    @property
    def supports_upload(self):
        return True

    @property
    def client_type(self):
        return "minimal"


async def test_base_client_default_set_unlimited_delegates_to_set_speed_limits_zero():
    client = _MinimalClient()
    await client.set_unlimited()
    assert client.calls == [(0, 0)]


async def test_sabnzbd_set_unlimited_writes_speedlimit_zero():
    """SABnzbd's set_unlimited must bypass set_speed_limits' issue-#43 1 KB/s floor."""
    client = SABnzbdClient("http://localhost:8080", "apikey")
    client._api_call = AsyncMock(return_value={})
    await client.set_unlimited()
    args, _ = client._api_call.call_args
    assert args[0] == "config"
    assert args[1] == {"name": "speedlimit", "value": "0"}
