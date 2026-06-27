"""Emby media server adapter."""
from typing import Dict

from app.clients.jellyfin_base import JellyfinBaseServer


class EmbyServer(JellyfinBaseServer):
    """Emby adapter (X-Emby-Token auth)."""

    type = "emby"

    def _auth_headers(self) -> Dict[str, str]:
        return {"X-Emby-Token": self.api_key}
