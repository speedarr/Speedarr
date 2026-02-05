"""
API clients for external services.
"""
from typing import TYPE_CHECKING
from app.clients.plex import PlexClient
from app.clients.qbittorrent import QBittorrentClient
from app.clients.sabnzbd import SABnzbdClient
from app.clients.nzbget import NZBGetClient
from app.clients.transmission import TransmissionClient
from app.clients.deluge import DelugeClient
from app.clients.base import BaseDownloadClient

if TYPE_CHECKING:
    from app.config import DownloadClientConfig

__all__ = [
    "PlexClient",
    "QBittorrentClient",
    "SABnzbdClient",
    "NZBGetClient",
    "TransmissionClient",
    "DelugeClient",
    "BaseDownloadClient",
    "create_download_client",
    "DOWNLOAD_CLIENT_TYPES",
]

# Map of client type to client class and required fields
DOWNLOAD_CLIENT_TYPES = {
    "qbittorrent": {
        "class": QBittorrentClient,
        "name": "qBittorrent",
        "supports_upload": True,
        "auth_type": "username_password",
        "color": "#3b82f6",
        "fields": ["url", "username", "password"],
    },
    "sabnzbd": {
        "class": SABnzbdClient,
        "name": "SABnzbd",
        "supports_upload": False,
        "auth_type": "api_key",
        "color": "#facc15",
        "fields": ["url", "api_key"],
    },
    "nzbget": {
        "class": NZBGetClient,
        "name": "NZBGet",
        "supports_upload": False,
        "auth_type": "username_password",
        "color": "#22c55e",
        "fields": ["url", "username", "password"],
    },
    "transmission": {
        "class": TransmissionClient,
        "name": "Transmission",
        "supports_upload": True,
        "auth_type": "username_password",
        "color": "#ef4444",
        "fields": ["url", "username", "password"],
    },
    "deluge": {
        "class": DelugeClient,
        "name": "Deluge",
        "supports_upload": True,
        "auth_type": "password",
        "color": "#8b5cf6",
        "fields": ["url", "password"],
    },
}


def create_download_client(config: "DownloadClientConfig") -> BaseDownloadClient:
    """
    Factory function to create a download client based on configuration.

    Args:
        config: DownloadClientConfig instance

    Returns:
        Appropriate download client instance

    Raises:
        ValueError: If client type is unknown
    """
    client_type = config.type.lower()

    if client_type not in DOWNLOAD_CLIENT_TYPES:
        raise ValueError(f"Unknown download client type: {client_type}")

    type_info = DOWNLOAD_CLIENT_TYPES[client_type]
    client_class = type_info["class"]

    # Build kwargs based on client type
    if client_type == "qbittorrent":
        return QBittorrentClient(
            url=config.url,
            username=config.username,
            password=config.password
        )
    elif client_type == "sabnzbd":
        return SABnzbdClient(
            url=config.url,
            api_key=config.api_key
        )
    elif client_type == "nzbget":
        return NZBGetClient(
            client_id=config.id,
            name=config.name,
            url=config.url,
            username=config.username,
            password=config.password
        )
    elif client_type == "transmission":
        return TransmissionClient(
            client_id=config.id,
            name=config.name,
            url=config.url,
            username=config.username,
            password=config.password
        )
    elif client_type == "deluge":
        return DelugeClient(
            client_id=config.id,
            name=config.name,
            url=config.url,
            password=config.password
        )
    else:
        raise ValueError(f"Unknown download client type: {client_type}")
