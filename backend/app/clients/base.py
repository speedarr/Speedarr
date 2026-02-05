"""
Base download client interface.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import aiohttp
from loguru import logger


class BaseDownloadClient(ABC):
    """Abstract base class for download clients."""

    def __init__(self, client_id: str, name: str, url: str):
        self.client_id = client_id
        self.name = name
        self.url = url.rstrip("/")
        self._session: Optional[aiohttp.ClientSession] = None
        self._original_limits: Optional[Dict[str, float]] = None

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

    async def restore_speed_limits(self):
        """Restore original speed limits."""
        if self._original_limits:
            await self.set_speed_limits(
                download_limit=self._original_limits.get("download_limit"),
                upload_limit=self._original_limits.get("upload_limit")
            )
            logger.debug(f"Restored {self.name} to original limits")

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
