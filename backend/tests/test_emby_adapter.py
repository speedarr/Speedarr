from app.clients.emby import EmbyServer
from app.clients.jellyfin_base import JellyfinBaseServer
from app.config import MediaServerConfig


def test_emby_is_jellyfin_base_with_emby_headers():
    s = EmbyServer(MediaServerConfig(id="e1", name="Emby", type="emby", url="http://emby:8096", api_key="secret"))
    assert isinstance(s, JellyfinBaseServer)
    assert s.type == "emby"
    assert s._auth_headers() == {"X-Emby-Token": "secret"}
