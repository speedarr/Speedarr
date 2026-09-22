"""Media-server outages: a silent server's last-known streams stay reserved for the
Media Server Timeout (failsafe.plex_timeout), then count as ended — partial or total (#102)."""
import asyncio
import pytest
from pydantic import ValidationError

from app.config import FailsafeConfig
from app.services.config_manager import validate_config
from app.services.polling_monitor import PollingMonitor
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


class FakeNotifier:
    def __init__(self):
        self.messages = []
    async def notify(self, event, message, data=None):
        self.messages.append((event, message, data))


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


def _cycle_monitor(servers):
    """A monitor that can run _plex_poll_cycle; stopped streams are recorded, not held."""
    pm = _monitor_with(servers)
    pm._cached_streams = []
    pm._first_poll = False
    pm.stopped = []

    async def record(stream):
        pm.stopped.append(stream)

    pm._handle_stopped_stream = record
    return pm


def _ids(streams):
    return sorted(s["session_id"] for s in streams)


# --- the one knob -----------------------------------------------------------

def test_media_server_timeout_defaults_to_300_and_rejects_negative():
    assert FailsafeConfig().plex_timeout == 300
    with pytest.raises(ValidationError):
        FailsafeConfig(plex_timeout=-1)


def test_grace_field_is_gone_and_a_stale_stored_key_is_ignored():
    assert "server_hold_grace_seconds" not in FailsafeConfig.model_fields
    cfg = FailsafeConfig(server_hold_grace_seconds=120, plex_timeout=45)
    assert cfg.plex_timeout == 45


def test_short_timeout_warning_talks_about_media_servers():
    cfg = make_config()
    cfg.failsafe.plex_timeout = 30
    warnings = [w for w in validate_config(cfg) if "timeout" in w.lower()]
    assert len(warnings) == 1
    assert warnings[0].startswith("Media server timeout")


# --- per-server hold --------------------------------------------------------

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
async def test_poll_one_failure_holds_last_streams_within_timeout():
    s = FakeServer("a", streams=[{"session_id": "a:1"}])
    pm = _monitor_with([s])
    await pm._poll_one(s)                 # success: records last_streams
    s.fail = True
    reachable, streams = await pm._poll_one(s)
    assert reachable is False
    assert len(streams) == 1             # held within the timeout (default 300 s)


@pytest.mark.asyncio
async def test_poll_one_failure_drops_after_media_server_timeout():
    s = FakeServer("a", streams=[{"session_id": "a:1"}])
    pm = _monitor_with([s])
    pm.config.failsafe.plex_timeout = 0   # drop immediately
    await pm._poll_one(s)
    s.fail = True
    reachable, streams = await pm._poll_one(s)
    assert reachable is False
    assert streams == []


@pytest.mark.asyncio
async def test_unreachable_notification_names_the_timeout():
    s = FakeServer("a", streams=[{"session_id": "a:1"}])
    pm = _monitor_with([s])
    pm.notification_service = FakeNotifier()
    await pm._poll_one(s)
    s.fail = True
    for _ in range(pm._plex_max_failures + 1):
        await pm._poll_one(s)
    unreachable = [m for e, m, _ in pm.notification_service.messages if e == "service_unreachable"]
    assert len(unreachable) == 1
    assert "limits maintained" not in unreachable[0].lower()
    assert "300 s" in unreachable[0]


# --- total outage -----------------------------------------------------------

@pytest.mark.asyncio
async def test_total_outage_within_timeout_keeps_streams_reserved():
    s = FakeServer("a", streams=[{"session_id": "a:1"}])
    pm = _cycle_monitor([s])
    await pm._plex_poll_cycle()                      # server up: stream cached
    assert _ids(pm._cached_streams) == ["a:1"]
    s.fail = True
    await pm._plex_poll_cycle()                      # everything down, inside the timeout
    assert _ids(pm._cached_streams) == ["a:1"]
    assert pm.stopped == []


@pytest.mark.asyncio
async def test_total_outage_past_timeout_drops_streams_as_stopped():
    s = FakeServer("a", streams=[{"session_id": "a:1"}])
    pm = _cycle_monitor([s])
    pm.config.failsafe.plex_timeout = 0
    await pm._plex_poll_cycle()
    s.fail = True
    await pm._plex_poll_cycle()
    assert pm._cached_streams == []
    assert _ids(pm.stopped) == ["a:1"]


@pytest.mark.asyncio
async def test_total_outage_past_timeout_applies_to_every_server():
    a = FakeServer("a", streams=[{"session_id": "a:1"}])
    b = FakeServer("b", streams=[{"session_id": "b:1"}])
    pm = _cycle_monitor([a, b])
    pm.config.failsafe.plex_timeout = 0
    await pm._plex_poll_cycle()
    a.fail = b.fail = True
    await pm._plex_poll_cycle()
    assert pm._cached_streams == []
    assert _ids(pm.stopped) == ["a:1", "b:1"]


@pytest.mark.asyncio
async def test_startup_during_total_outage_keeps_first_poll_pending():
    """A restart mid-outage must not turn the server's existing streams into 'started' events."""
    s = FakeServer("a", streams=[{"session_id": "a:1"}], fail=True)
    pm = _cycle_monitor([s])
    pm._first_poll = True
    await pm._plex_poll_cycle()
    assert pm._first_poll is True
    assert pm._cached_streams == []
    s.fail = False
    await pm._plex_poll_cycle()                      # first answer: existing streams, no started/stopped handling
    assert pm._first_poll is False
    assert _ids(pm._cached_streams) == ["a:1"]
