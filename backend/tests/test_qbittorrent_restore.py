"""qBittorrent restore must re-apply original limits, including unlimited (0)."""
import asyncio
from unittest.mock import AsyncMock

from app.clients.qbittorrent import QBittorrentClient


def _client():
    return QBittorrentClient("http://localhost:8080", "admin", "pw")


def test_restore_reapplies_unlimited_as_zero():
    client = _client()
    client._original_limits = {"download_limit": 0, "upload_limit": 0}
    client.set_speed_limits = AsyncMock()
    asyncio.run(client.restore_speed_limits())
    client.set_speed_limits.assert_awaited_once_with(download_limit=0, upload_limit=0)


def test_restore_reapplies_nonzero_originals():
    client = _client()
    client._original_limits = {"download_limit": 25.0, "upload_limit": 10.0}
    client.set_speed_limits = AsyncMock()
    asyncio.run(client.restore_speed_limits())
    client.set_speed_limits.assert_awaited_once_with(download_limit=25.0, upload_limit=10.0)


def test_restore_noop_when_no_originals_captured():
    client = _client()
    client._original_limits = None
    client.set_speed_limits = AsyncMock()
    asyncio.run(client.restore_speed_limits())
    client.set_speed_limits.assert_not_awaited()
