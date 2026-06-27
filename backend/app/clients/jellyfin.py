"""Jellyfin media server adapter (built; not surfaced in the UI yet)."""
from typing import Dict

from app.clients.jellyfin_base import JellyfinBaseServer


class JellyfinServer(JellyfinBaseServer):
    """Jellyfin adapter (MediaBrowser token auth)."""

    type = "jellyfin"

    def _auth_headers(self) -> Dict[str, str]:
        return {"Authorization": f'MediaBrowser Token="{self.api_key}"'}
