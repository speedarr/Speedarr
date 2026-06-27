from app.clients.jellyfin import JellyfinServer
from app.clients.jellyfin_base import JellyfinBaseServer
from app.config import MediaServerConfig


def test_jellyfin_auth_header():
    s = JellyfinServer(MediaServerConfig(id="j1", name="Jellyfin", type="jellyfin", url="http://jf:8096", api_key="abc"))
    assert isinstance(s, JellyfinBaseServer)
    assert s.type == "jellyfin"
    assert s._auth_headers() == {"Authorization": 'MediaBrowser Token="abc"'}
