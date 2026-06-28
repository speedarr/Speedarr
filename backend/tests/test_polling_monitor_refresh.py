import pytest
from app.services.polling_monitor import PollingMonitor


class _SpyServer:
    def __init__(self):
        self.refreshed = 0
    async def refresh_lan_subnets(self):
        self.refreshed += 1
    async def close(self):
        pass


@pytest.mark.asyncio
async def test_start_refreshes_lan_subnets_for_each_server(monkeypatch):
    # Build a bare monitor without running __init__ (it needs many collaborators)
    pm = PollingMonitor.__new__(PollingMonitor)
    s1, s2 = _SpyServer(), _SpyServer()
    pm.media_servers = {"a": s1, "b": s2}
    pm._download_task = None
    pm._plex_task = None

    # Neutralize the poll loops so start() only exercises the refresh + task spawn
    async def _noop_loop():
        return None
    monkeypatch.setattr(pm, "_download_poll_loop", _noop_loop)
    monkeypatch.setattr(pm, "_plex_poll_loop", _noop_loop)

    await pm.start()
    assert s1.refreshed == 1 and s2.refreshed == 1
