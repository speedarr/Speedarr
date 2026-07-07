"""Factory for creating media server adapters from config."""
from app.clients.base_media_server import BaseMediaServer
from app.clients.plex import PlexClient
from app.clients.emby import EmbyServer
from app.clients.jellyfin import JellyfinServer
from app.config import MediaServerConfig

_REGISTRY = {
    "plex": PlexClient,
    "emby": EmbyServer,
    "jellyfin": JellyfinServer,
}


def create_media_server(cfg: MediaServerConfig) -> BaseMediaServer:
    """Create a media server adapter for the given config."""
    cls = _REGISTRY.get(cfg.type)
    if cls is None:
        raise ValueError(f"Unknown media server type: {cfg.type!r}")
    return cls(cfg)
