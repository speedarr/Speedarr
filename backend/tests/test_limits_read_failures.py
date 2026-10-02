"""A failed limits read fails the poll instead of reading as unlimited (audit T4-5, ruling 5),
and NZBGet goes back to the cap saved in its own settings."""
import asyncio
from unittest.mock import AsyncMock

import aiohttp
import pytest

from app.clients.deluge import DelugeClient
from app.clients.nzbget import NZBGetClient
from app.clients.qbittorrent import QBittorrentClient
from app.clients.sabnzbd import SABnzbdClient
from app.clients.transmission import TransmissionClient
from app.services.decision_engine import DecisionEngine
from tests.conftest import dl, make_config, stats

QB, NZB = "qbittorrent_1", "nzbget_1"


class _Resp:
    def __init__(self, text="", json=None):
        self._text, self._json = text, json

    def raise_for_status(self):
        pass

    async def text(self):
        return self._text

    async def json(self):
        return self._json


def _nzbget_half_reachable():
    """status answers, the second status call (the limits read) times out - the T3-1 observation."""
    client = NZBGetClient(NZB, "NZBGet", "http://localhost:6789", "u", "p")
    calls = {"n": 0}

    async def rpc(method, params=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"DownloadRate": 0, "DownloadLimit": 0, "DownloadedSizeMB": 0}
        raise asyncio.TimeoutError()

    client._rpc_call = AsyncMock(side_effect=rpc)
    return client


async def test_nzbget_half_reachable_returns_the_error_dict():
    stats_ = await _nzbget_half_reachable().get_stats()
    assert "error" in stats_ and "download_limit" not in stats_


async def test_nzbget_half_reachable_is_held_out_past_the_sixth_poll():
    """Before: zeros read as a healthy idle client, demoted to the safety net on poll 6, qB got ~855."""
    nzb_stats = await _nzbget_half_reachable().get_stats()
    engine = DecisionEngine(make_config(download_total=900.0))
    poll = {**stats(download={QB: 400.0}), NZB: {**nzb_stats, "supports_upload": False}}
    decisions = None
    for _ in range(8):
        decisions = engine.calculate_throttle(active_streams=[], download_stats=poll)
    assert dl(decisions, QB) <= 450.0 + 1e-6


async def test_qbittorrent_failed_limits_read_fails_the_poll():
    client = QBittorrentClient("http://localhost:8080", "admin", "pw")

    async def request(method, endpoint, **kwargs):
        if endpoint == "/api/v2/transfer/info":
            return _Resp(json={"dl_info_speed": 0, "up_info_speed": 0})
        raise aiohttp.ClientError("limits read timed out")

    client._request = AsyncMock(side_effect=request)
    stats_ = await client.get_stats()
    assert stats_["error"] == "limits read timed out" and "download_limit" not in stats_


async def test_transmission_failed_limits_read_fails_the_poll():
    client = TransmissionClient("transmission_1", "Transmission", "http://localhost:9091")
    calls = {"session-get": 0}

    async def rpc(method, arguments=None):
        if method == "session-stats":
            return {"downloadSpeed": 0, "uploadSpeed": 0}
        if method == "torrent-get":
            return {"torrents": []}
        if method == "session-get":
            calls["session-get"] += 1
            if calls["session-get"] == 2:      # the get_speed_limits read
                raise aiohttp.ClientError("down")
            return {}
        raise AssertionError(method)

    client._rpc_call = AsyncMock(side_effect=rpc)
    assert "error" in await client.get_stats()


async def test_deluge_failed_limits_read_fails_the_poll():
    client = DelugeClient("deluge_1", "Deluge", "http://localhost:8112", "pw")
    client._ensure_authenticated = AsyncMock()
    calls = {"core.get_config": 0}

    async def rpc(method, params=None, **kwargs):
        if method == "core.get_session_status":
            return {"download_rate": 0, "upload_rate": 0, "num_downloading": 0}
        if method == "core.get_config":
            calls["core.get_config"] += 1
            if calls["core.get_config"] == 2:  # the get_speed_limits read
                raise aiohttp.ClientError("down")
            return {}
        raise AssertionError(method)

    client._rpc_call = AsyncMock(side_effect=rpc)
    assert "error" in await client.get_stats()


@pytest.mark.parametrize("reply", [{}, None, {"status": False}])
async def test_sabnzbd_reply_without_a_queue_is_an_error(reply):
    client = SABnzbdClient("http://localhost:8080", "key")
    client._api_call = AsyncMock(return_value=reply)
    assert "error" in await client.get_stats()


@pytest.mark.parametrize("make", [
    lambda: QBittorrentClient("http://localhost:8080", "admin", "pw"),
    lambda: TransmissionClient("transmission_1", "Transmission", "http://localhost:9091"),
    lambda: DelugeClient("deluge_1", "Deluge", "http://localhost:8112", "pw"),
    lambda: NZBGetClient(NZB, "NZBGet", "http://localhost:6789", "u", "p"),
], ids=["qbittorrent", "transmission", "deluge", "nzbget"])
def test_no_adapter_keeps_original_limits(make):
    assert not hasattr(make(), "_original_limits")


def _nzbget_with_config(options):
    client = NZBGetClient(NZB, "NZBGet", "http://localhost:6789", "u", "p")

    async def rpc(method, params=None):
        if method == "config":
            return options
        return True

    client._rpc_call = AsyncMock(side_effect=rpc)
    return client


async def test_nzbget_restore_writes_its_saved_download_rate():
    client = _nzbget_with_config([{"Name": "ControlPort", "Value": "6789"},
                                  {"Name": "DownloadRate", "Value": "1221"}])
    limits = await client.restore_speed_limits(None)
    client._rpc_call.assert_any_await("rate", [1221])
    assert limits["download_limit"] == pytest.approx(1221 * 1024 * 8 / 1e6)
    assert limits["upload_limit"] == 0.0


async def test_nzbget_restore_of_zero_is_unlimited():
    client = _nzbget_with_config([{"Name": "DownloadRate", "Value": "0"}])
    assert await client.restore_speed_limits({"download_limit": 9.0, "upload_limit": 0.0}) == {
        "download_limit": 0.0, "upload_limit": 0.0}
    client._rpc_call.assert_any_await("rate", [0])


async def test_nzbget_restore_without_download_rate_raises_and_writes_nothing():
    client = _nzbget_with_config([{"Name": "ControlPort", "Value": "6789"}])
    with pytest.raises(ValueError):
        await client.restore_speed_limits(None)
    assert all(c.args[0] != "rate" for c in client._rpc_call.await_args_list)
