"""Every adapter's restore reports what it did: limits written, None, or an exception (audit D3-3)."""
from unittest.mock import AsyncMock

import aiohttp
import pytest

from app.clients.base import RestoreOutcome
from app.clients.deluge import DelugeClient
from app.clients.nzbget import NZBGetClient
from app.clients.qbittorrent import QBittorrentClient
from app.clients.sabnzbd import SABnzbdClient
from app.clients.transmission import TransmissionClient

BASELINE = {"download_limit": 25.0, "upload_limit": 10.0}

TORRENT = {
    "qbittorrent": lambda: QBittorrentClient("http://localhost:8080", "admin", "pw"),
    "transmission": lambda: TransmissionClient("transmission_1", "Transmission", "http://localhost:9091"),
    "deluge": lambda: DelugeClient("deluge_1", "Deluge", "http://localhost:8112", "pw"),
}


def test_restore_outcome_values_are_the_api_strings():
    assert [o.value for o in RestoreOutcome] == ["restored", "nothing_to_restore", "failed"]


@pytest.mark.parametrize("make", TORRENT.values(), ids=TORRENT.keys())
def test_torrent_clients_do_not_restore_a_saved_cap(make):
    assert make().restores_saved_cap is False


def test_usenet_clients_restore_their_saved_cap():
    assert SABnzbdClient("http://localhost:8080", "key").restores_saved_cap is True
    assert NZBGetClient("nzbget_1", "NZBGet", "http://localhost:6789", "u", "p").restores_saved_cap is True


@pytest.mark.parametrize("make", TORRENT.values(), ids=TORRENT.keys())
async def test_torrent_restore_writes_the_baseline_and_returns_it(make):
    client = make()
    client.set_speed_limits = AsyncMock()
    assert await client.restore_speed_limits(BASELINE) == BASELINE
    client.set_speed_limits.assert_awaited_once_with(download_limit=25.0, upload_limit=10.0)


@pytest.mark.parametrize("make", TORRENT.values(), ids=TORRENT.keys())
async def test_torrent_restore_reapplies_unlimited_explicitly(make):
    client = make()
    client.set_speed_limits = AsyncMock()
    zero = {"download_limit": 0.0, "upload_limit": 0.0}
    assert await client.restore_speed_limits(zero) == zero
    client.set_speed_limits.assert_awaited_once_with(download_limit=0.0, upload_limit=0.0)


@pytest.mark.parametrize("make", TORRENT.values(), ids=TORRENT.keys())
async def test_torrent_restore_without_baseline_is_nothing_and_makes_no_call(make):
    client = make()
    client.set_speed_limits = AsyncMock()
    assert await client.restore_speed_limits(None) is None
    client.set_speed_limits.assert_not_awaited()


@pytest.mark.parametrize("make", TORRENT.values(), ids=TORRENT.keys())
async def test_torrent_restore_ignores_extra_record_fields(make):
    client = make()
    client.set_speed_limits = AsyncMock()
    record = {**BASELINE, "url": "http://x", "captured_at": "2026-10-02T00:00:00+00:00"}
    assert await client.restore_speed_limits(record) == BASELINE
    client.set_speed_limits.assert_awaited_once_with(download_limit=25.0, upload_limit=10.0)


@pytest.mark.parametrize("make", TORRENT.values(), ids=TORRENT.keys())
async def test_torrent_restore_raises_when_the_write_fails(make):
    client = make()
    client.set_speed_limits = AsyncMock(side_effect=aiohttp.ClientError("down"))
    with pytest.raises(aiohttp.ClientError):
        await client.restore_speed_limits(BASELINE)


async def test_sabnzbd_restore_raises_instead_of_swallowing():
    """The audit's shutdown log: 'Failed to restore speed limit' then 'Restored sabnzbd_… to normal speeds'."""
    client = SABnzbdClient("http://sab.audit.invalid", "key")
    client._api_call = AsyncMock(side_effect=aiohttp.ClientError("sab.audit.invalid/api"))
    with pytest.raises(aiohttp.ClientError):
        await client.restore_speed_limits(None)


async def test_nzbget_restore_without_a_capture_is_nothing():
    """Interim until Task 8 (NZBGet then reads DownloadRate)."""
    client = NZBGetClient("nzbget_1", "NZBGet", "http://localhost:6789", "u", "p")
    client._rpc_call = AsyncMock()
    assert await client.restore_speed_limits(None) is None
    client._rpc_call.assert_not_awaited()
