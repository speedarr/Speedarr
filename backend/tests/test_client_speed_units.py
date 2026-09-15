"""Every adapter must apply the limit Speedarr asked for, in the client's own unit.

The app works in decimal Mbps. 10 Mbps is 1,250,000 bytes/s. Clients that count a
kilobyte as 1024 bytes (qBittorrent's UI, NZBGet, Deluge, SABnzbd's "K" suffix) must
receive 1220.7 KiB/s, not 1250; clients that count 1000 (Transmission) receive 1250.
Reading a limit or a live speed back must return the same decimal Mbps figure.
"""
import asyncio
from unittest.mock import AsyncMock

import pytest

from app.clients.deluge import DelugeClient
from app.clients.nzbget import NZBGetClient
from app.clients.qbittorrent import QBittorrentClient
from app.clients.sabnzbd import SABnzbdClient
from app.clients.transmission import TransmissionClient

TEN_MBPS_BYTES = 1_250_000
TEN_MBPS_KIB = 1_250_000 / 1024  # 1220.703125


def _run(coro):
    return asyncio.run(coro)


def _as_mbps_from_kib(kib):
    """What a 1024-based client actually enforces, restated in decimal Mbps."""
    return kib * 1024 * 8 / 1_000_000


# ---------------------------------------------------------------- qBittorrent

class _Resp:
    def __init__(self, text="", json=None):
        self._text = text
        self._json = json

    def raise_for_status(self):
        pass

    async def text(self):
        return self._text

    async def json(self):
        return self._json


def _qbit():
    return QBittorrentClient("http://localhost:8080", "admin", "pw")


def test_qbittorrent_sets_decimal_bytes_per_sec():
    client = _qbit()
    client._request = AsyncMock(return_value=_Resp())
    _run(client.set_speed_limits(download_limit=10.0, upload_limit=2.0))
    calls = {c.args[1]: c.kwargs["data"]["limit"] for c in client._request.call_args_list}
    assert calls["/api/v2/transfer/setDownloadLimit"] == str(TEN_MBPS_BYTES)
    assert calls["/api/v2/transfer/setUploadLimit"] == str(250_000)


def test_qbittorrent_reads_limits_as_decimal_mbps():
    client = _qbit()
    client._request = AsyncMock(return_value=_Resp(text=str(TEN_MBPS_BYTES)))
    limits = _run(client.get_speed_limits())
    assert limits["download_limit"] == pytest.approx(10.0)
    assert limits["upload_limit"] == pytest.approx(10.0)


def test_qbittorrent_reads_live_speed_as_decimal_mbps():
    client = _qbit()

    async def request(method, endpoint, **kwargs):
        if endpoint == "/api/v2/transfer/info":
            return _Resp(json={"dl_info_speed": TEN_MBPS_BYTES, "up_info_speed": 0})
        return _Resp(text="0")

    client._request = AsyncMock(side_effect=request)
    stats = _run(client.get_stats())
    assert stats["download_speed"] == pytest.approx(10.0)


# --------------------------------------------------------------------- NZBGet

def _nzbget():
    return NZBGetClient("nzbget_1", "NZBGet", "http://localhost:6789", "user", "pw")


def test_nzbget_sets_kibibytes_per_sec():
    client = _nzbget()
    client._rpc_call = AsyncMock(return_value=True)
    _run(client.set_speed_limits(download_limit=10.0))
    method, params = client._rpc_call.call_args.args
    assert method == "rate"
    assert _as_mbps_from_kib(params[0]) == pytest.approx(10.0, rel=1e-3)


def test_nzbget_reads_limit_and_speed_as_decimal_mbps():
    client = _nzbget()
    client._rpc_call = AsyncMock(return_value={
        "DownloadLimit": TEN_MBPS_BYTES,
        "DownloadRate": TEN_MBPS_BYTES,
        "DownloadedSizeMB": 1,
    })
    stats = _run(client.get_stats())
    assert stats["download_limit"] == pytest.approx(10.0)
    assert stats["download_speed"] == pytest.approx(10.0)


# --------------------------------------------------------------------- Deluge

def _deluge():
    client = DelugeClient("deluge_1", "Deluge", "http://localhost:8112", "pw")
    client._ensure_authenticated = AsyncMock()
    return client


def test_deluge_sets_kibibytes_per_sec():
    client = _deluge()
    client._rpc_call = AsyncMock(return_value=None)
    _run(client.set_speed_limits(download_limit=10.0, upload_limit=2.0))
    method, params = client._rpc_call.call_args.args
    assert method == "core.set_config"
    assert _as_mbps_from_kib(params[0]["max_download_speed"]) == pytest.approx(10.0, rel=1e-3)
    assert _as_mbps_from_kib(params[0]["max_upload_speed"]) == pytest.approx(2.0, rel=1e-3)


def test_deluge_unlimited_stays_minus_one():
    client = _deluge()
    client._rpc_call = AsyncMock(return_value=None)
    _run(client.set_speed_limits(download_limit=0, upload_limit=0))
    _, params = client._rpc_call.call_args.args
    assert params[0] == {"max_download_speed": -1.0, "max_upload_speed": -1.0}


def test_deluge_reads_limits_and_speed_as_decimal_mbps():
    client = _deluge()

    async def rpc(method, params=None, **kwargs):
        if method == "core.get_session_status":
            return {"download_rate": TEN_MBPS_BYTES, "upload_rate": 0, "num_downloading": 1}
        if method == "core.get_config":
            return {"max_download_speed": TEN_MBPS_KIB, "max_upload_speed": -1}
        raise AssertionError(method)

    client._rpc_call = AsyncMock(side_effect=rpc)
    stats = _run(client.get_stats())
    assert stats["download_limit"] == pytest.approx(10.0)
    assert stats["upload_limit"] == 0
    assert stats["download_speed"] == pytest.approx(10.0)


# --------------------------------------------------------------- Transmission

def _transmission():
    return TransmissionClient("transmission_1", "Transmission", "http://localhost:9091")


def test_transmission_sets_decimal_kilobytes_per_sec():
    client = _transmission()
    client._rpc_call = AsyncMock(return_value={})
    _run(client.set_speed_limits(download_limit=10.0))
    method, args = client._rpc_call.call_args.args
    assert method == "session-set"
    assert args["speed-limit-down"] == 1250
    assert args["speed-limit-down-enabled"] is True


def test_transmission_reads_limit_and_speed_as_decimal_mbps():
    client = _transmission()

    async def rpc(method, arguments=None):
        if method == "session-stats":
            return {"downloadSpeed": TEN_MBPS_BYTES, "uploadSpeed": 0}
        if method == "session-get":
            return {"speed-limit-down-enabled": True, "speed-limit-down": 1250,
                    "speed-limit-up-enabled": False, "speed-limit-up": 0}
        if method == "torrent-get":
            return {"torrents": []}
        raise AssertionError(method)

    client._rpc_call = AsyncMock(side_effect=rpc)
    stats = _run(client.get_stats())
    assert stats["download_limit"] == pytest.approx(10.0)
    assert stats["download_speed"] == pytest.approx(10.0)


# -------------------------------------------------------------------- SABnzbd

def _sabnzbd():
    return SABnzbdClient("http://localhost:8080", "apikey")


def test_sabnzbd_sets_kibibytes_with_k_suffix():
    client = _sabnzbd()
    client._api_call = AsyncMock(return_value={})
    _run(client.set_speed_limits(download_limit=10.0))
    value = client._api_call.call_args.args[1]["value"]
    assert value.endswith("K")
    assert _as_mbps_from_kib(int(value[:-1])) == pytest.approx(10.0, rel=1e-3)


def test_sabnzbd_reads_limit_and_speed_as_decimal_mbps():
    client = _sabnzbd()
    client._api_call = AsyncMock(return_value={"queue": {
        "kbpersec": f"{TEN_MBPS_KIB:.2f}",   # SABnzbd reports KiB/s
        "speedlimit_abs": str(TEN_MBPS_BYTES),  # bytes/s
        "noofslots": 1,
    }})
    stats = _run(client.get_stats())
    assert stats["download_limit"] == pytest.approx(10.0)
    assert stats["download_speed"] == pytest.approx(10.0, rel=1e-3)


def test_sabnzbd_limit_survives_a_write_read_round_trip():
    """Set 10 Mbps, let SABnzbd store it as bytes (K = 1024), read it back: still 10."""
    client = _sabnzbd()
    client._api_call = AsyncMock(return_value={})
    _run(client.set_speed_limits(download_limit=10.0))
    sent = client._api_call.call_args.args[1]["value"]
    stored_bytes = int(sent[:-1]) * 1024

    client._api_call = AsyncMock(return_value={"queue": {
        "kbpersec": "0", "speedlimit_abs": str(stored_bytes), "noofslots": 0,
    }})
    stats = _run(client.get_stats())
    assert stats["download_limit"] == pytest.approx(10.0, rel=1e-3)
