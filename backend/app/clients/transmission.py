"""
Transmission API client for monitoring and controlling downloads.
"""
from typing import Dict, Any, Optional
import aiohttp
from loguru import logger
from .base import BaseDownloadClient
from app.utils.bandwidth import bytes_per_sec_to_mbps, kilobytes_per_sec_to_mbps, mbps_to_kilobytes_per_sec


class TransmissionClient(BaseDownloadClient):
    """Client for interacting with Transmission RPC API."""

    def __init__(self, client_id: str, name: str, url: str, username: str = None, password: str = None):
        super().__init__(client_id, name, url)
        self.username = username
        self.password = password
        self._session_id: Optional[str] = None

    @property
    def supports_upload(self) -> bool:
        return True

    @property
    def client_type(self) -> str:
        return "transmission"

    async def _rpc_call(self, method: str, arguments: dict = None) -> Any:
        """Make an RPC call to Transmission."""
        payload = {
            "method": method,
            "arguments": arguments or {}
        }

        headers = {}
        if self._session_id:
            headers["X-Transmission-Session-Id"] = self._session_id

        auth = None
        if self.username and self.password:
            auth = aiohttp.BasicAuth(self.username, self.password)

        async with self.session.post(
            f"{self.url}/transmission/rpc",
            json=payload,
            headers=headers,
            auth=auth
        ) as response:
            # Transmission returns 409 with session ID on first request
            if response.status == 409:
                self._session_id = response.headers.get("X-Transmission-Session-Id")
                return await self._rpc_call(method, arguments)

            response.raise_for_status()
            result = await response.json()

            if result.get("result") != "success":
                raise Exception(f"Transmission RPC error: {result.get('result')}")

            return result.get("arguments", {})

    async def test_connection(self) -> bool:
        """Test connection and authentication."""
        try:
            await self._rpc_call("session-get")
            return True
        except Exception as e:
            logger.error(f"Transmission connection test failed: {e}")
            return False

    async def get_stats(self) -> Dict[str, Any]:
        """Get current transfer statistics."""
        try:
            # Get session stats
            session = await self._rpc_call("session-stats")

            # Get session settings for limits
            settings = await self._rpc_call("session-get")

            # Get torrents to count active downloads
            torrents_result = await self._rpc_call("torrent-get", {
                "fields": ["status", "rateDownload", "rateUpload"]
            })
            torrents = torrents_result.get("torrents", [])

            # Count actively downloading (status 4 = downloading)
            downloading_count = sum(1 for t in torrents if t.get("status") == 4)

            # Transmission reports speeds in bytes/sec
            download_speed = bytes_per_sec_to_mbps(session.get("downloadSpeed", 0))
            upload_speed = bytes_per_sec_to_mbps(session.get("uploadSpeed", 0))

            # Get speed limits
            speed_limits = await self.get_speed_limits()

            # Store original limits if not already stored
            if self._original_limits is None:
                self._original_limits = speed_limits.copy()

            return {
                "active": session.get("downloadSpeed", 0) > 0 or session.get("uploadSpeed", 0) > 0,
                "download_speed": download_speed,
                "upload_speed": upload_speed,
                "downloading_count": downloading_count,
                "download_limit": speed_limits.get("download_limit", 0),
                "upload_limit": speed_limits.get("upload_limit", 0),
                "original_download_limit": self._original_limits.get("download_limit", 0),
                "original_upload_limit": self._original_limits.get("upload_limit", 0),
            }
        except Exception as e:
            logger.error(f"Failed to get Transmission stats: {e}")
            return {"active": False, "error": str(e)}

    async def get_speed_limits(self) -> Dict[str, float]:
        """Get current speed limits in Mbps."""
        try:
            settings = await self._rpc_call("session-get")

            # Transmission uses KB/s (1 KB = 1000 bytes) for limits
            dl_enabled = settings.get("speed-limit-down-enabled", False)
            ul_enabled = settings.get("speed-limit-up-enabled", False)

            dl_limit_kbps = settings.get("speed-limit-down", 0) if dl_enabled else 0
            ul_limit_kbps = settings.get("speed-limit-up", 0) if ul_enabled else 0

            return {
                "download_limit": kilobytes_per_sec_to_mbps(dl_limit_kbps) if dl_limit_kbps > 0 else 0,
                "upload_limit": kilobytes_per_sec_to_mbps(ul_limit_kbps) if ul_limit_kbps > 0 else 0,
            }
        except Exception as e:
            logger.error(f"Failed to get Transmission speed limits: {e}")
            return {"download_limit": 0, "upload_limit": 0}

    async def set_speed_limits(self, download_limit: Optional[float] = None, upload_limit: Optional[float] = None):
        """Set speed limits in Mbps."""
        try:
            arguments = {}

            if download_limit is not None:
                # Transmission counts 1 KB as 1000 bytes
                limit_kbps = int(mbps_to_kilobytes_per_sec(download_limit))
                arguments["speed-limit-down"] = limit_kbps
                arguments["speed-limit-down-enabled"] = limit_kbps > 0

            if upload_limit is not None:
                limit_kbps = int(mbps_to_kilobytes_per_sec(upload_limit))
                arguments["speed-limit-up"] = limit_kbps
                arguments["speed-limit-up-enabled"] = limit_kbps > 0

            if arguments:
                await self._rpc_call("session-set", arguments)
                logger.debug(f"Set Transmission limits: DL={download_limit} Mbps, UL={upload_limit} Mbps")

        except Exception as e:
            logger.error(f"Failed to set Transmission speed limits: {e}")
            raise
