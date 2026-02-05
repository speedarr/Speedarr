"""
Deluge API client for monitoring and controlling downloads.
"""
from typing import Dict, Any, Optional
import aiohttp
from loguru import logger
from .base import BaseDownloadClient


class DelugeClient(BaseDownloadClient):
    """Client for interacting with Deluge Web API (JSON-RPC)."""

    def __init__(self, client_id: str, name: str, url: str, password: str):
        super().__init__(client_id, name, url)
        self.password = password
        self._authenticated = False
        self._request_id = 0
        self._session_cookie: Optional[str] = None

    @property
    def supports_upload(self) -> bool:
        return True

    @property
    def client_type(self) -> str:
        return "deluge"

    async def _get_request_id(self) -> int:
        """Get next request ID."""
        self._request_id += 1
        return self._request_id

    async def _rpc_call(self, method: str, params: list = None, retry_auth: bool = True) -> Any:
        """Make a JSON-RPC call to Deluge."""
        payload = {
            "method": method,
            "params": params or [],
            "id": await self._get_request_id()
        }

        # Build headers with session cookie if we have one
        headers = {"Content-Type": "application/json"}
        if self._session_cookie:
            headers["Cookie"] = self._session_cookie

        async with self.session.post(
            f"{self.url}/json",
            json=payload,
            headers=headers
        ) as response:
            response.raise_for_status()

            # Capture session cookie from response
            if "Set-Cookie" in response.headers:
                cookie_header = response.headers["Set-Cookie"]
                # Extract just the cookie name=value part
                if "_session_id=" in cookie_header:
                    self._session_cookie = cookie_header.split(";")[0]
                    logger.debug(f"Captured Deluge session cookie")

            result = await response.json()

            if result.get("error"):
                error = result["error"]
                # Check if this is an authentication error
                if isinstance(error, dict) and error.get("code") == 1 and "Not authenticated" in str(error.get("message", "")):
                    # Session expired, reset auth flag and cookie
                    self._authenticated = False
                    self._session_cookie = None
                    if retry_auth and method != "auth.login":
                        # Try to re-authenticate and retry the call
                        logger.debug("Deluge session expired, re-authenticating...")
                        await self._ensure_authenticated()
                        return await self._rpc_call(method, params, retry_auth=False)
                raise Exception(f"Deluge RPC error: {error}")

            return result.get("result")

    async def _ensure_authenticated(self):
        """Ensure we have a valid authentication session."""
        if self._authenticated:
            # Verify session is still valid
            try:
                result = await self._rpc_call("auth.check_session", retry_auth=False)
                if result:
                    return
                # Session expired
                self._authenticated = False
                logger.debug("Deluge session expired, re-authenticating")
            except Exception as e:
                logger.debug(f"Error checking Deluge session: {e}")
                self._authenticated = False

        try:
            # Login to Deluge Web UI
            logger.debug(f"Authenticating with Deluge at {self.url}")
            result = await self._rpc_call("auth.login", [self.password], retry_auth=False)

            if not result:
                raise Exception("Authentication failed - check password")

            if not self._session_cookie:
                raise Exception("Login succeeded but no session cookie received")

            self._authenticated = True
            logger.debug("Authenticated with Deluge Web UI")

            # Check if already connected to daemon (common when Web UI is pre-configured)
            try:
                connected = await self._rpc_call("web.connected", retry_auth=False)
                if connected:
                    logger.debug("Already connected to Deluge daemon")
                    return

                # Not connected, try to connect
                daemons = await self._rpc_call("web.get_hosts", retry_auth=False)
                if daemons:
                    host_id = daemons[0][0]
                    await self._rpc_call("web.connect", [host_id], retry_auth=False)
                    logger.debug(f"Connected to Deluge daemon: {host_id}")
                else:
                    logger.warning("No Deluge daemons configured in Web UI - please add a daemon in Deluge Connection Manager")
            except Exception as e:
                # Check if we can still make core calls (some setups work without explicit connect)
                try:
                    await self._rpc_call("core.get_libtorrent_version", retry_auth=False)
                    logger.debug("Deluge daemon accessible without explicit connect")
                except Exception:
                    logger.warning(f"Failed to connect to Deluge daemon: {e}. Ensure daemon is running and Web UI is connected to it.")

        except Exception as e:
            self._authenticated = False
            logger.error(f"Failed to authenticate with Deluge: {e}")
            raise

    async def test_connection(self) -> bool:
        """Test connection and authentication."""
        try:
            await self._ensure_authenticated()
            return True
        except Exception as e:
            logger.error(f"Deluge connection test failed: {e}")
            return False

    async def get_stats(self) -> Dict[str, Any]:
        """Get current transfer statistics."""
        await self._ensure_authenticated()

        try:
            # Get session status
            status = await self._rpc_call("core.get_session_status", [
                ["download_rate", "upload_rate", "num_downloading"]
            ])

            # Get config for limits
            config = await self._rpc_call("core.get_config")

            # Deluge reports speeds in bytes/sec
            download_speed = status.get("download_rate", 0) / 1_048_576 * 8
            upload_speed = status.get("upload_rate", 0) / 1_048_576 * 8

            # Get speed limits
            speed_limits = await self.get_speed_limits()

            # Store original limits if not already stored
            if self._original_limits is None:
                self._original_limits = speed_limits.copy()

            return {
                "active": status.get("download_rate", 0) > 0 or status.get("upload_rate", 0) > 0,
                "download_speed": download_speed,
                "upload_speed": upload_speed,
                "downloading_count": status.get("num_downloading", 0),
                "download_limit": speed_limits.get("download_limit", 0),
                "upload_limit": speed_limits.get("upload_limit", 0),
                "original_download_limit": self._original_limits.get("download_limit", 0),
                "original_upload_limit": self._original_limits.get("upload_limit", 0),
            }
        except Exception as e:
            logger.error(f"Failed to get Deluge stats: {e}")
            return {"active": False, "error": str(e)}

    async def get_speed_limits(self) -> Dict[str, float]:
        """Get current speed limits in Mbps."""
        await self._ensure_authenticated()

        try:
            config = await self._rpc_call("core.get_config")

            # Deluge uses bytes/sec for limits, -1 means unlimited
            dl_limit = config.get("max_download_speed", -1)
            ul_limit = config.get("max_upload_speed", -1)

            return {
                "download_limit": (dl_limit * 8 / 1000) if dl_limit > 0 else 0,
                "upload_limit": (ul_limit * 8 / 1000) if ul_limit > 0 else 0,
            }
        except Exception as e:
            logger.error(f"Failed to get Deluge speed limits: {e}")
            return {"download_limit": 0, "upload_limit": 0}

    async def set_speed_limits(self, download_limit: Optional[float] = None, upload_limit: Optional[float] = None):
        """Set speed limits in Mbps."""
        await self._ensure_authenticated()

        try:
            config_updates = {}

            if download_limit is not None:
                # Convert Mbps to KB/s (Deluge uses KB/s in config)
                limit_kbps = float(download_limit * 1000 / 8) if download_limit > 0 else -1.0
                config_updates["max_download_speed"] = limit_kbps

            if upload_limit is not None:
                limit_kbps = float(upload_limit * 1000 / 8) if upload_limit > 0 else -1.0
                config_updates["max_upload_speed"] = limit_kbps

            if config_updates:
                await self._rpc_call("core.set_config", [config_updates])
                logger.debug(f"Set Deluge limits: DL={download_limit} Mbps, UL={upload_limit} Mbps")

        except Exception as e:
            logger.error(f"Failed to set Deluge speed limits: {e}")
            raise
