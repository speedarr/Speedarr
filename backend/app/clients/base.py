"""
Base download client interface.
"""
from abc import ABC, abstractmethod
from enum import Enum
from typing import Dict, Any, Optional
import aiohttp
from loguru import logger


class RestoreOutcome(str, Enum):
    """What a restore did for one client (audit D3-3)."""
    RESTORED = "restored"
    NOTHING_TO_RESTORE = "nothing_to_restore"
    FAILED = "failed"


class BaseDownloadClient(ABC):
    """Abstract base class for download clients."""

    def __init__(self, client_id: str, name: str, url: str):
        self.client_id = client_id
        self.name = name
        self.url = url.rstrip("/")
        self._session: Optional[aiohttp.ClientSession] = None

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

    @abstractmethod
    async def test_connection(self) -> bool:
        """Test connection and authentication."""
        pass

    @abstractmethod
    async def get_stats(self) -> Dict[str, Any]:
        """Get current transfer statistics."""
        pass

    @abstractmethod
    async def get_speed_limits(self) -> Dict[str, float]:
        """Get current speed limits in Mbps."""
        pass

    @abstractmethod
    async def set_speed_limits(self, download_limit: Optional[float] = None, upload_limit: Optional[float] = None):
        """Set speed limits in Mbps."""
        pass

    @property
    def restores_saved_cap(self) -> bool:
        """True when the client keeps its own saved cap apart from the limit in force (SABnzbd, NZBGet)."""
        return False

    async def restore_speed_limits(self, baseline: Optional[Dict[str, float]] = None) -> Optional[Dict[str, float]]:
        """Write the baseline back and return it; None when there is no baseline. Raises on failure."""
        if baseline is None:
            return None
        limits = {"download_limit": baseline["download_limit"], "upload_limit": baseline["upload_limit"]}
        await self.set_speed_limits(**limits)
        logger.debug(f"Restored {self.name} to its normal limits")
        return limits

    async def set_unlimited(self):
        """Remove all speed limits. Default: 0 maps to native unlimited."""
        await self.set_speed_limits(download_limit=0, upload_limit=0)

    @property
    @abstractmethod
    def supports_upload(self) -> bool:
        """Whether this client supports upload management."""
        pass

    @property
    @abstractmethod
    def client_type(self) -> str:
        """The type identifier for this client."""
        pass
