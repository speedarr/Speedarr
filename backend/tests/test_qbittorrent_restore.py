"""qBittorrent restore re-applies the baseline it is handed, including unlimited (0)."""
from unittest.mock import AsyncMock

from app.clients.qbittorrent import QBittorrentClient


def _client():
    return QBittorrentClient("http://localhost:8080", "admin", "pw")


async def test_restore_reapplies_unlimited_as_zero():
    client = _client()
    client.set_speed_limits = AsyncMock()
    await client.restore_speed_limits({"download_limit": 0, "upload_limit": 0})
    client.set_speed_limits.assert_awaited_once_with(download_limit=0, upload_limit=0)


async def test_restore_reapplies_nonzero_baseline():
    client = _client()
    client.set_speed_limits = AsyncMock()
    await client.restore_speed_limits({"download_limit": 25.0, "upload_limit": 10.0})
    client.set_speed_limits.assert_awaited_once_with(download_limit=25.0, upload_limit=10.0)


async def test_restore_noop_without_baseline():
    client = _client()
    client.set_speed_limits = AsyncMock()
    assert await client.restore_speed_limits(None) is None
    client.set_speed_limits.assert_not_awaited()
