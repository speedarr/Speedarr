"""
Base media server interface (Plex, Emby, Jellyfin).

Mirrors BaseDownloadClient: each concrete adapter manages its own aiohttp
session and implements test_connection()/get_active_streams().
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

import aiohttp

from app.config import MediaServerConfig


class BaseMediaServer(ABC):
    """Abstract base class for media servers."""

    type: str = ""  # "plex" | "emby" | "jellyfin" — overridden by subclasses

    def __init__(self, cfg: MediaServerConfig):
        self.server_id = cfg.id
        self.name = cfg.name
        self.url = cfg.url.rstrip("/")
        self.include_lan_streams = cfg.include_lan_streams
        self._session: Optional[aiohttp.ClientSession] = None

    async def close(self) -> None:
        """Close the HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()

    @abstractmethod
    async def test_connection(self) -> bool:
        """Test connection and authentication. Never raises; returns bool."""
        ...

    @abstractmethod
    async def get_active_streams(self) -> List[Dict[str, Any]]:
        """
        Return active streams as normalized dicts.

        MUST raise on connection error / timeout / auth failure (the polling
        monitor counts failures on the raise). MUST return [] when reachable
        but no one is streaming.
        """
        ...

    def _finalize_stream(self, stream: Dict[str, Any], raw_session_id: Any) -> Dict[str, Any]:
        """Inject server attribution and make session_id globally unique."""
        stream["server_id"] = self.server_id
        stream["server_name"] = self.name
        stream["server_type"] = self.type
        stream["session_id"] = f"{self.server_id}:{raw_session_id}"
        return stream
