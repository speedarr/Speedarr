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


def _session(address, location="", local=None):
    sess = {
        "type": "movie", "title": "X",
        "Session": {"id": "r1", "bandwidth": 8000},
        "Media": [{"bitrate": 8000, "videoResolution": "1080"}],
        "User": {"id": "u1", "title": "bob"},
        "Player": {"state": "playing", "title": "p", "address": address},
    }
    if location:
        sess["Session"]["location"] = location
    if local is not None:
        sess["Session"]["local"] = local
    return sess


def _client_with(lan_networks):
    return PlexClient(MediaServerConfig(id="plex", name="Plex", type="plex",
                                        url="http://plex:32400", token="tok",
                                        lan_networks=lan_networks))


def test_plex_default_marks_private_ip_lan():
    out = _client()._normalize_stream(_session("192.168.10.158"), actual_bandwidth_mbps=0.0)
    assert out["is_lan"] is True


def test_plex_override_marks_out_of_range_private_ip_wan():
    c = _client_with(["192.168.5.0/24"])
    out = c._normalize_stream(_session("192.168.10.158"), actual_bandwidth_mbps=0.0)
    assert out["is_lan"] is False


def test_plex_server_local_flag_wins_over_override():
    c = _client_with(["192.168.5.0/24"])
    out = c._normalize_stream(_session("192.168.10.158", local="1"), actual_bandwidth_mbps=0.0)
    assert out["is_lan"] is True


def _session_res(video_resolution):
    return {
        "type": "movie", "title": "X",
        "Session": {"id": "r1", "bandwidth": 8000},
        "Media": [{"bitrate": 8000, "videoResolution": video_resolution}],
        "User": {"id": "u1", "title": "bob"},
        "Player": {"state": "playing", "title": "p", "address": "1.2.3.4"},
    }


@pytest.mark.parametrize("video_resolution,expected", [
    ("1080", "1080p"),
    ("4k", "4K"),
    ("720", "720p"),
    ("480", "480p"),
    ("sd", "SD"),
    ("", None),
    (None, None),
])
def test_plex_quality_profile_normalized(video_resolution, expected):
    out = _client()._normalize_stream(_session_res(video_resolution), actual_bandwidth_mbps=0.0)
    assert out["quality_profile"] == expected
