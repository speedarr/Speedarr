"""Shared Emby/Jellyfin /Sessions normalization."""
from app.clients.jellyfin_base import JellyfinBaseServer
from app.config import MediaServerConfig


class _Concrete(JellyfinBaseServer):
    type = "emby"
    def _auth_headers(self):
        return {"X-Emby-Token": self.api_key}


def _srv(include_lan=False):
    return _Concrete(MediaServerConfig(id="e1", name="Emby", type="emby",
                                       url="http://emby:8096", api_key="k",
                                       include_lan_streams=include_lan))


def test_bitrate_converted_from_bps_to_mbps():
    raw = {
        "Id": "sess9",
        "NowPlayingItem": {"Type": "Movie", "MediaStreams": [{"Type": "Video", "BitRate": 8_000_000}]},
        "PlayState": {"IsPaused": False},
        "RemoteEndPoint": "203.0.113.5",
        "UserName": "bob",
    }
    out = _srv()._normalize_session(raw)
    assert out["stream_bitrate_mbps"] == 8.0     # 8_000_000 bps -> 8 Mbps (NOT 8000)
    assert out["stream_bandwidth_mbps"] == 0.0   # no /statistics/bandwidth equivalent
    assert out["media_type"] == "movie"          # lowercased
    assert out["session_id"] == "e1:sess9"
    assert out["server_id"] == "e1"


def test_media_type_audio_maps_to_track():
    raw = {"Id": "s", "NowPlayingItem": {"Type": "Audio", "MediaStreams": []}, "PlayState": {}, "RemoteEndPoint": "8.8.8.8"}
    assert _srv()._normalize_session(raw)["media_type"] == "track"


def test_transcoding_bitrate_fallback():
    raw = {"Id": "s", "NowPlayingItem": {"Type": "Episode", "MediaStreams": []},
           "TranscodingInfo": {"Bitrate": 5_000_000}, "PlayState": {}, "RemoteEndPoint": "8.8.8.8"}
    assert _srv()._normalize_session(raw)["stream_bitrate_mbps"] == 5.0


def test_is_lan_from_private_remote_endpoint():
    raw = {"Id": "s", "NowPlayingItem": {"Type": "Movie", "MediaStreams": []}, "PlayState": {}, "RemoteEndPoint": "192.168.1.20"}
    assert _srv()._normalize_session(raw)["is_lan"] is True


def test_is_lan_from_islocal_flag():
    raw = {"Id": "s", "NowPlayingItem": {"Type": "Movie", "MediaStreams": []}, "PlayState": {}, "IsLocal": True, "RemoteEndPoint": "203.0.113.5"}
    assert _srv()._normalize_session(raw)["is_lan"] is True


def test_is_lan_from_bare_ipv6():
    # fe80::1 is link-local; ipaddress treats it as private
    raw = {"Id": "s", "NowPlayingItem": {"Type": "Movie", "MediaStreams": []}, "PlayState": {}, "RemoteEndPoint": "fe80::1"}
    assert _srv()._normalize_session(raw)["is_lan"] is True


def test_is_lan_from_bracketed_ipv6_with_port():
    # fd00::/8 is ULA (Unique Local Address); ipaddress treats it as private
    raw = {"Id": "s", "NowPlayingItem": {"Type": "Movie", "MediaStreams": []}, "PlayState": {}, "RemoteEndPoint": "[fd00::5]:8096"}
    assert _srv()._normalize_session(raw)["is_lan"] is True


def test_wan_public_ipv4_with_port():
    # 8.8.8.8 is Google DNS (genuinely public); is_private=False, exercises ipv4:port parsing
    raw = {"Id": "s", "NowPlayingItem": {"Type": "Movie", "MediaStreams": []}, "PlayState": {}, "RemoteEndPoint": "8.8.8.8:54321"}
    assert _srv()._normalize_session(raw)["is_lan"] is False


def test_media_type_musicvideo_maps_to_track():
    raw = {"Id": "s", "NowPlayingItem": {"Type": "MusicVideo", "MediaStreams": []}, "PlayState": {}, "RemoteEndPoint": "8.8.8.8"}
    assert _srv()._normalize_session(raw)["media_type"] == "track"
