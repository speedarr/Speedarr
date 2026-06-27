"""PlexClient refactored onto BaseMediaServer."""
import pytest
from app.clients.plex import PlexClient
from app.clients.base_media_server import BaseMediaServer
from app.config import MediaServerConfig


def _client():
    return PlexClient(MediaServerConfig(id="plex", name="Plex", type="plex", url="http://plex:32400", token="tok"))


def test_plexclient_is_base_media_server():
    c = _client()
    assert isinstance(c, BaseMediaServer)
    assert c.type == "plex"
    assert c.server_id == "plex" and c.token == "tok"


def test_normalize_injects_server_id_and_prefixes_session_id():
    c = _client()
    session = {
        "type": "movie",
        "title": "Blade Runner",
        "Session": {"id": "raw123", "bandwidth": 8000},   # 8000 kbps -> 8 Mbps
        "Media": [{"bitrate": 8000, "videoResolution": "1080"}],
        "User": {"id": "u1", "title": "alice"},
        "Player": {"state": "playing", "title": "Shield", "address": "1.2.3.4"},
    }
    out = c._normalize_stream(session, actual_bandwidth_mbps=0.0)
    assert out["server_id"] == "plex"
    assert out["session_id"] == "plex:raw123"
    assert out["stream_bitrate_mbps"] == 8.0
    assert out["media_type"] == "movie"


@pytest.mark.asyncio
async def test_get_active_streams_propagates_unreachable(monkeypatch):
    c = _client()

    async def boom():
        raise ConnectionError("down")
    monkeypatch.setattr(c, "_get_sessions", boom)
    with pytest.raises(ConnectionError):
        await c.get_active_streams()
