"""
SABnzbd API client for monitoring and controlling Usenet downloads.
"""
from typing import Dict, Any, Optional
import aiohttp
from loguru import logger


class SABnzbdClient:
    """Client for interacting with SABnzbd API."""

    def __init__(self, url: str, api_key: str):
        self.url = url.rstrip("/")
        self.api_key = api_key
        self._session: Optional[aiohttp.ClientSession] = None
        self._original_limit: Optional[float] = None

    @property
    def session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=2)
            )
        return self._session

    async def close(self):
        """Close the HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()

    async def test_connection(self) -> bool:
        """Test connection to SABnzbd."""
        try:
            response = await self._api_call("version")
            return "version" in response
        except Exception as e:
            logger.error(f"SABnzbd connection test failed: {e}")
            return False

    async def get_stats(self) -> Dict[str, Any]:
        """Get current download statistics."""
        try:
            response = await self._api_call("queue")

            if not response or "queue" not in response:
                return {"active": False}

            # Access the nested queue object
            queue = response["queue"]

            # Extract speed (KB/s as float)
            speed_kbps = float(queue.get("kbpersec", 0))
            speed_mbps = (speed_kbps / 1024) * 8  # KB/s to Mbps

            # Get speed limit using speedlimit_abs which is in bytes per second
            # This is the actual effective limit regardless of how it was set
            speedlimit_abs = queue.get("speedlimit_abs", "0")
            speedlimit_bytes = float(speedlimit_abs) if speedlimit_abs else 0
            # Convert bytes/s to Mbps using binary (1024*1024 = 1048576)
            # bytes/s * 8 / 1048576 = Mbps, simplified: bytes/s / 131072
            limit_mbps = (speedlimit_bytes * 8) / (1024 * 1024) if speedlimit_bytes > 0 else 0

            # Store original limit
            if self._original_limit is None and limit_mbps > 0:
                self._original_limit = limit_mbps

            queue_size = queue.get("noofslots", 0)

            # Determine if actually downloading based on speed, not queue status
            # Queue can have items but be paused or idle
            downloading_count = 1 if speed_kbps > 1 else 0  # > 1 KB/s = actively downloading

            return {
                "active": speed_kbps > 0,
                "download_speed": speed_mbps,
                "download_limit": limit_mbps,
                "original_download_limit": self._original_limit or 0,
                "upload_speed": 0,  # SABnzbd doesn't upload
                "upload_limit": 0,
                "queue_size": queue_size,
                "downloading_count": downloading_count,
            }

        except Exception as e:
            logger.error(f"Failed to get SABnzbd stats: {e}")
            return {"active": False, "error": str(e)}

    async def set_speed_limits(self, download_limit: Optional[float] = None, upload_limit: Optional[float] = None):
        """Set speed limit for downloads (upload ignored).

        First sets percentage to 100% to clear any percentage-based throttling,
        then sets the absolute speed limit in MB/s.
        """
        if download_limit is None:
            return

        try:
            # Set absolute speed limit using value with M suffix for MB/s
            # Convert Mbps to MB/s (divide by 8)
            mb_per_sec = download_limit / 8
            value = f"{mb_per_sec:.1f}M"
            await self._api_call("config", {"name": "speedlimit", "value": value})

            logger.debug(f"Set SABnzbd download limit: {download_limit:.1f} Mbps ({mb_per_sec:.1f} MB/s)")

        except Exception as e:
            logger.error(f"Failed to set SABnzbd speed limit: {e}")
            raise

    async def restore_speed_limits(self):
        """Restore original speed limit."""
        try:
            # Set to 0 to remove limit (unlimited)
            await self._api_call("config", {"name": "speedlimit", "value": "0"})
            logger.debug("Removed SABnzbd speed limit (unlimited)")
        except Exception as e:
            logger.error(f"Failed to restore speed limit: {e}")

    async def _api_call(self, mode: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """Execute a SABnzbd API call."""
        api_params = {
            "apikey": self.api_key,
            "mode": mode,
            "output": "json",
        }

        if params:
            api_params.update(params)

        url = f"{self.url}/api"

        try:
            async with self.session.get(url, params=api_params) as response:
                response.raise_for_status()
                return await response.json()
        except aiohttp.ClientError as e:
            logger.error(f"SABnzbd API call failed: {e}")
            raise
