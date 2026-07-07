"""Shared Emby/Jellyfin /Sessions normalization + LAN classification."""
import pytest
from app.clients.jellyfin_base import JellyfinBaseServer
from app.config import MediaServerConfig


class _Concrete(JellyfinBaseServer):
    type = "emby"
    _network_config_path = "/System/Configuration"
    def _auth_headers(self):
        return {"X-Emby-Token": self.api_key}


def _srv(include_lan=False, lan_networks=None):
    return _Concrete(MediaServerConfig(id="e1", name="Emby", type="emby",
                                       url="http://emby:8096", api_key="k",
                                       include_lan_streams=include_lan,
                                       lan_networks=lan_networks or []))


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


def _playing(remote, **extra):
    raw = {"Id": "s", "NowPlayingItem": {"Type": "Movie", "MediaStreams": []},
           "PlayState": {}, "RemoteEndPoint": remote}
    raw.update(extra)
    return raw


def test_auto_subnets_classify_outside_subnet_as_wan():
    # The real bug: client 192.168.10.158 outside server LAN 192.168.5.0/24 -> WAN
    s = _srv()
    s._auto_subnets = ["192.168.5.0/24"]
    assert s._normalize_session(_playing("192.168.10.158"))["is_lan"] is False
    assert s._normalize_session(_playing("192.168.5.42"))["is_lan"] is True


def test_manual_override_wins_over_auto_and_heuristic():
    s = _srv(lan_networks=["10.0.0.0/8"])
    s._auto_subnets = ["192.168.5.0/24"]
    # 192.168.5.42 is in auto but NOT in the manual override -> WAN
    assert s._normalize_session(_playing("192.168.5.42"))["is_lan"] is False
    # 10.1.2.3 is in the manual override -> LAN
    assert s._normalize_session(_playing("10.1.2.3"))["is_lan"] is True


def test_falls_back_to_private_ip_when_no_config():
    s = _srv()  # no manual, no auto
    assert s._normalize_session(_playing("192.168.1.20"))["is_lan"] is True
    assert s._normalize_session(_playing("8.8.8.8"))["is_lan"] is False


def test_islocal_flag_still_forces_lan():
    # Server-provided local flag is OR'd in, even for a public IP and empty config
    s = _srv()
    assert s._normalize_session(_playing("203.0.113.5", IsLocal=True))["is_lan"] is True


def test_parse_network_config_extracts_subnets():
    data = {"LocalNetworkSubnets": ["192.168.5.0/24", " 10.0.0.0/8 ", ""]}
    assert _Concrete._parse_network_config(data) == ["192.168.5.0/24", "10.0.0.0/8"]


def test_parse_network_config_handles_missing_and_nonlist():
    assert _Concrete._parse_network_config({}) == []
    assert _Concrete._parse_network_config({"LocalNetworkSubnets": None}) == []
    assert _Concrete._parse_network_config("not-a-dict") == []  # type: ignore[arg-type]


class _FakeResp:
    def __init__(self, status, payload):
        self.status = status
        self._payload = payload
    async def __aenter__(self):
        return self
    async def __aexit__(self, *a):
        return False
    async def json(self, content_type=None):
        return self._payload


class _FakeSession:
    def __init__(self, resp=None, exc=None):
        self._resp, self._exc = resp, exc
    def get(self, url, headers=None):
        if self._exc:
            raise self._exc
        return self._resp


@pytest.mark.asyncio
async def test_refresh_lan_subnets_populates_cache(monkeypatch):
    s = _srv()
    monkeypatch.setattr(type(s), "session",
                        property(lambda self: _FakeSession(
                            _FakeResp(200, {"LocalNetworkSubnets": ["192.168.5.0/24"]}))))
    await s.refresh_lan_subnets()
    assert s._auto_subnets == ["192.168.5.0/24"]


@pytest.mark.asyncio
async def test_refresh_lan_subnets_never_raises_and_keeps_cache(monkeypatch):
    s = _srv()
    s._auto_subnets = ["192.168.5.0/24"]
    # Non-200 -> cache unchanged
    monkeypatch.setattr(type(s), "session",
                        property(lambda self: _FakeSession(_FakeResp(401, {}))))
    await s.refresh_lan_subnets()
    assert s._auto_subnets == ["192.168.5.0/24"]
    # Exception -> cache unchanged, no raise
    monkeypatch.setattr(type(s), "session",
                        property(lambda self: _FakeSession(exc=RuntimeError("boom"))))
    await s.refresh_lan_subnets()
    assert s._auto_subnets == ["192.168.5.0/24"]


@pytest.mark.asyncio
async def test_refresh_noop_when_no_endpoint(monkeypatch):
    s = _srv()
    monkeypatch.setattr(type(s), "_network_config_path", "")
    await s.refresh_lan_subnets()   # must not even touch the session
    assert s._auto_subnets == []


def test_quality_from_video_stream_display_title():
    raw = {
        "Id": "s", "PlayState": {}, "RemoteEndPoint": "8.8.8.8",
        "NowPlayingItem": {"Type": "Movie", "MediaStreams": [
            {"Type": "Audio", "DisplayTitle": "English - AAC - Stereo - Default"},
            {"Type": "Video", "DisplayTitle": "1080p H264 SDR", "BitRate": 8_000_000},
        ]},
    }
    # Picks the Video stream (not index 0, which is Audio here) and canonicalizes.
    assert _srv()._normalize_session(raw)["quality_profile"] == "1080p"


def test_quality_strips_leaked_title_from_display_title():
    raw = {
        "Id": "s", "PlayState": {}, "RemoteEndPoint": "8.8.8.8",
        "NowPlayingItem": {"Type": "Movie", "MediaStreams": [
            {"Type": "Video", "DisplayTitle": "All Good Things - 1080p - H264 - SDR"},
        ]},
    }
    assert _srv()._normalize_session(raw)["quality_profile"] == "1080p"


def test_quality_none_when_no_video_stream():
    raw = {
        "Id": "s", "PlayState": {}, "RemoteEndPoint": "8.8.8.8",
        "NowPlayingItem": {"Type": "Audio", "MediaStreams": [
            {"Type": "Audio", "DisplayTitle": "English - AAC - Stereo"},
        ]},
    }
    assert _srv()._normalize_session(raw)["quality_profile"] is None


def test_quality_uhd_display_title_maps_to_4k():
    raw = {
        "Id": "s", "PlayState": {}, "RemoteEndPoint": "8.8.8.8",
        "NowPlayingItem": {"Type": "Movie", "MediaStreams": [
            {"Type": "Video", "DisplayTitle": "4K HEVC Dolby Vision"},
        ]},
    }
    assert _srv()._normalize_session(raw)["quality_profile"] == "4K"
