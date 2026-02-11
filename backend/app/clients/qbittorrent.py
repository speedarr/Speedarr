"""
qBittorrent API client for monitoring and controlling downloads.
"""
from typing import Dict, Any, Optional
import aiohttp
from loguru import logger


class QBittorrentClient:
    """Client for interacting with qBittorrent Web API."""

    def __init__(self, url: str, username: str, password: str):
        self.url = url.rstrip("/")
        self.username = username
        self.password = password
        self._session: Optional[aiohttp.ClientSession] = None
        self._authenticated = False
        self._original_limits: Optional[Dict[str, float]] = None

    @property
    def session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                cookie_jar=aiohttp.CookieJar(unsafe=True),
                timeout=aiohttp.ClientTimeout(total=2)
            )
        return self._session

    async def close(self):
        """Close the HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()

    async def test_connection(self) -> bool:
        """Test connection and authentication."""
        try:
            await self._ensure_authenticated()
            return True
        except Exception as e:
            logger.error(f"qBittorrent connection test failed: {e}")
            return False

    async def _ensure_authenticated(self):
        """Ensure we have a valid authentication session."""
        if self._authenticated:
            return

        try:
            data = {"username": self.username, "password": self.password}

            async with self.session.post(f"{self.url}/api/v2/auth/login", data=data) as response:
                if response.status == 200:
                    text = await response.text()
                    if text.strip() == "Ok.":
                        self._authenticated = True
                        logger.debug("Authenticated with qBittorrent")
                    else:
                        raise Exception("qBittorrent login rejected (credentials may be wrong)")
                else:
                    raise Exception(f"Authentication failed with status {response.status}")
        except Exception as e:
            logger.error(f"Failed to authenticate with qBittorrent: {e}")
            raise

    async def _request(self, method: str, endpoint: str, retry_on_auth_failure: bool = True, **kwargs):
        """Make HTTP request with automatic re-authentication on 403."""
        await self._ensure_authenticated()
        url = f"{self.url}{endpoint}"
        response = await self.session.request(method, url, **kwargs)

        if response.status == 403 and retry_on_auth_failure:
            await response.release()
            logger.info("qBittorrent returned 403, re-authenticating...")
            self._authenticated = False
            await self._ensure_authenticated()
            response = await self.session.request(method, url, **kwargs)

        return response

    async def get_stats(self) -> Dict[str, Any]:
        """Get current transfer statistics."""
        try:
            # Get transfer info
            response = await self._request("GET", "/api/v2/transfer/info")
            response.raise_for_status()
            transfer_info = await response.json()

            # Determine if actually downloading based on speed, not torrent state
            # A torrent can be in "downloading" state but stalled with no data transfer
            download_speed_bytes = transfer_info.get("dl_info_speed", 0)
            downloading_count = 1 if download_speed_bytes > 1024 else 0  # > 1KB/s = actively downloading

            # Get current speed limits
            speed_limits = await self.get_speed_limits()

            # Store original limits if not already stored
            if self._original_limits is None:
                self._original_limits = speed_limits.copy()

            return {
                "active": transfer_info.get("dl_info_speed", 0) > 0 or transfer_info.get("up_info_speed", 0) > 0,
                "download_speed": transfer_info.get("dl_info_speed", 0) / 1_048_576 * 8,  # bytes/s to Mbps
                "upload_speed": transfer_info.get("up_info_speed", 0) / 1_048_576 * 8,
                "downloading_count": downloading_count,
                "download_limit": speed_limits.get("download_limit", 0),
                "upload_limit": speed_limits.get("upload_limit", 0),
                "original_download_limit": self._original_limits.get("download_limit", 0),
                "original_upload_limit": self._original_limits.get("upload_limit", 0),
            }

        except Exception as e:
            logger.error(f"Failed to get qBittorrent stats: {e}")
            return {"active": False, "error": str(e)}

    async def get_speed_limits(self) -> Dict[str, float]:
        """Get current speed limits in Mbps."""
        try:
            response = await self._request("GET", "/api/v2/transfer/downloadLimit")
            response.raise_for_status()
            dl_limit_text = await response.text()
            dl_limit_bytes = int(dl_limit_text.strip())

            response = await self._request("GET", "/api/v2/transfer/uploadLimit")
            response.raise_for_status()
            ul_limit_text = await response.text()
            ul_limit_bytes = int(ul_limit_text.strip())

            # Convert bytes/sec to Mbps (0 means unlimited in qBit)
            return {
                "download_limit": (dl_limit_bytes / 1_048_576 * 8) if dl_limit_bytes > 0 else 0,
                "upload_limit": (ul_limit_bytes / 1_048_576 * 8) if ul_limit_bytes > 0 else 0,
            }
        except Exception as e:
            logger.error(f"Failed to get speed limits: {e}")
            return {"download_limit": 0, "upload_limit": 0}

    async def set_speed_limits(self, download_limit: Optional[float] = None, upload_limit: Optional[float] = None):
        """Set speed limits in Mbps."""
        try:
            if download_limit is not None:
                # Convert Mbps to bytes/second
                limit_bytes = int(download_limit * 1_048_576 / 8)
                response = await self._request("POST", "/api/v2/transfer/setDownloadLimit", data={"limit": str(limit_bytes)})
                response.raise_for_status()

            if upload_limit is not None:
                limit_bytes = int(upload_limit * 1_048_576 / 8)
                response = await self._request("POST", "/api/v2/transfer/setUploadLimit", data={"limit": str(limit_bytes)})
                response.raise_for_status()

            logger.debug(f"Set qBittorrent limits: DL={download_limit} Mbps, UL={upload_limit} Mbps")

        except Exception as e:
            logger.error(f"Failed to set speed limits: {e}")
            raise

    async def restore_speed_limits(self):
        """Restore original speed limits."""
        if self._original_limits:
            await self.set_speed_limits(
                download_limit=self._original_limits["download_limit"] if self._original_limits["download_limit"] > 0 else None,
                upload_limit=self._original_limits["upload_limit"] if self._original_limits["upload_limit"] > 0 else None
            )
            logger.debug("Restored qBittorrent to original limits")
