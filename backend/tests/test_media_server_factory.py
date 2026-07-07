"""Media server factory dispatch."""
import pytest
from app.clients.media_server_factory import create_media_server
from app.clients.plex import PlexClient
from app.config import MediaServerConfig


def test_creates_plex():
    s = create_media_server(MediaServerConfig(id="plex", name="Plex", type="plex", url="http://p:32400", token="t"))
    assert isinstance(s, PlexClient)
    assert s.server_id == "plex"


def test_unknown_type_raises():
    with pytest.raises(ValueError):
        create_media_server(MediaServerConfig(id="x", name="x", type="nope", url="u"))


def test_creates_emby_and_jellyfin():
    from app.clients.emby import EmbyServer
    from app.clients.jellyfin import JellyfinServer
    e = create_media_server(MediaServerConfig(id="e", name="E", type="emby", url="http://e:8096", api_key="k"))
    j = create_media_server(MediaServerConfig(id="j", name="J", type="jellyfin", url="http://j:8096", api_key="k"))
    assert isinstance(e, EmbyServer)
    assert isinstance(j, JellyfinServer)
