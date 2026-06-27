"""Multi-server polling: per-server conservative hold + total-outage gate."""
import asyncio
import pytest

from app.services.polling_monitor import PollingMonitor
from app.config import MediaServerConfig
from tests.conftest import make_config


class FakeServer:
    def __init__(self, server_id, streams=None, fail=False, include_lan=False):
        self.server_id = server_id
        self.name = server_id
        self.type = "plex"
        self.include_lan_streams = include_lan
        self._streams = streams or []
        self.fail = fail
    async def get_active_streams(self):
        if self.fail:
            raise ConnectionError("down")
        return [dict(s) for s in self._streams]
    async def close(self):
        pass


def _monitor_with(servers):
    pm = PollingMonitor.__new__(PollingMonitor)   # bypass __init__/network
    pm.config = make_config()
    pm.media_servers = {s.server_id: s for s in servers}
    pm._server_state = {
        s.server_id: {"failures": 0, "warned": False, "last_streams": [], "last_success": None}
        for s in servers
    }
    pm.notification_service = None
    pm._plex_max_failures = 6
    return pm


@pytest.mark.asyncio
async def test_poll_one_success_tags_lan_policy_and_records_state():
    s = FakeServer("a", streams=[{"session_id": "a:1"}], include_lan=True)
    pm = _monitor_with([s])
    reachable, streams = await pm._poll_one(s)
    assert reachable is True
    assert streams[0]["include_lan_streams"] is True
    assert pm._server_state["a"]["failures"] == 0
    assert pm._server_state["a"]["last_streams"] == streams


@pytest.mark.asyncio
async def test_poll_one_failure_holds_last_streams_within_grace():
    s = FakeServer("a", streams=[{"session_id": "a:1"}])
    pm = _monitor_with([s])
    await pm._poll_one(s)                 # success: records last_streams
    s.fail = True
    reachable, streams = await pm._poll_one(s)
    assert reachable is False
    assert len(streams) == 1             # held within grace (default 300s)


@pytest.mark.asyncio
async def test_poll_one_failure_drops_after_grace():
    s = FakeServer("a", streams=[{"session_id": "a:1"}])
    pm = _monitor_with([s])
    pm.config.failsafe.server_hold_grace_seconds = 0   # immediate drop
    await pm._poll_one(s)
    s.fail = True
    reachable, streams = await pm._poll_one(s)
    assert reachable is False
    assert streams == []
