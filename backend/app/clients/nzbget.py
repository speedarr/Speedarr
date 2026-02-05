"""
NZBGet API client for monitoring and controlling downloads.
"""
from typing import Dict, Any, Optional
import aiohttp
from loguru import logger
from .base import BaseDownloadClient


class NZBGetClient(BaseDownloadClient):
    """Client for interacting with NZBGet JSON-RPC API."""

    def __init__(self, client_id: str, name: str, url: str, username: str, password: str):
        super().__init__(client_id, name, url)
        self.username = username
        self.password = password

    @property
    def supports_upload(self) -> bool:
        return False

    @property
    def client_type(self) -> str:
        return "nzbget"

    def _get_auth(self) -> aiohttp.BasicAuth:
        """Get basic auth credentials."""
        return aiohttp.BasicAuth(self.username, self.password)

    async def _rpc_call(self, method: str, params: list = None) -> Any:
        """Make a JSON-RPC call to NZBGet."""
        payload = {
            "method": method,
            "params": params or [],
            "id": 1,
            "jsonrpc": "2.0"
        }

        async with self.session.post(
            f"{self.url}/jsonrpc",
            json=payload,
            auth=self._get_auth()
        ) as response:
            response.raise_for_status()
            result = await response.json()
            if "error" in result:
                raise Exception(f"NZBGet RPC error: {result['error']}")
            return result.get("result")

    async def test_connection(self) -> bool:
        """Test connection and authentication."""
        try:
            await self._rpc_call("version")
            return True
        except Exception as e:
            logger.error(f"NZBGet connection test failed: {e}")
            return False

    async def get_stats(self) -> Dict[str, Any]:
        """Get current transfer statistics."""
        try:
            status = await self._rpc_call("status")

            # Get current speed limit
            speed_limits = await self.get_speed_limits()

            # Store original limits if not already stored
            if self._original_limits is None:
                self._original_limits = speed_limits.copy()

            # NZBGet reports speed in bytes/sec
            download_speed_mbps = status.get("DownloadRate", 0) / 1_048_576 * 8

            return {
                "active": status.get("DownloadRate", 0) > 0,
                "download_speed": download_speed_mbps,
                "upload_speed": 0,  # NZBGet doesn't upload
                "downloading_count": status.get("DownloadedSizeMB", 0) > 0,
                "download_limit": speed_limits.get("download_limit", 0),
                "upload_limit": 0,
                "original_download_limit": self._original_limits.get("download_limit", 0),
                "original_upload_limit": 0,
            }
        except Exception as e:
            logger.error(f"Failed to get NZBGet stats: {e}")
            return {"active": False, "error": str(e)}

    async def get_speed_limits(self) -> Dict[str, float]:
        """Get current speed limits in Mbps."""
        try:
            status = await self._rpc_call("status")
            # NZBGet uses DownloadLimit in bytes/sec, 0 means unlimited
            limit_bytes = status.get("DownloadLimit", 0)

            # Convert bytes/sec to Mbps (0 means unlimited, report as 0)
            if limit_bytes == 0:
                download_limit = 0  # Unlimited
            else:
                download_limit = limit_bytes / 1_048_576 * 8

            return {
                "download_limit": download_limit,
                "upload_limit": 0,
            }
        except Exception as e:
            logger.error(f"Failed to get NZBGet speed limits: {type(e).__name__}: {e}")
            return {"download_limit": 0, "upload_limit": 0}

    async def set_speed_limits(self, download_limit: Optional[float] = None, upload_limit: Optional[float] = None):
        """Set speed limits in Mbps."""
        try:
            if download_limit is not None:
                # Convert Mbps to KB/s (NZBGet uses KB/s)
                # 1 Mbps = 125 KB/s (1,000,000 bits / 8,000 bits per KB)
                limit_kbps = int(download_limit * 125)
                await self._rpc_call("rate", [limit_kbps])
                logger.debug(f"Set NZBGet download limit: {download_limit:.1f} Mbps ({limit_kbps} KB/s)")
        except Exception as e:
            logger.error(f"Failed to set NZBGet speed limits: {type(e).__name__}: {e}")
            raise
