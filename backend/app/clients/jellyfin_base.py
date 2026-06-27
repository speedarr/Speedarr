"""
Shared base for Emby and Jellyfin (Jellyfin is a fork of Emby).

Both expose GET /Sessions returning a JSON array of sessions with
NowPlayingItem / PlayState / TranscodingInfo / RemoteEndPoint / UserName.
Bitrates are in BPS (not kbps). There is no /statistics/bandwidth equivalent,
so stream_bandwidth_mbps is always 0.
"""
import ipaddress
from typing import Any, Dict, List, Optional

import aiohttp
from loguru import logger

from app.clients.base_media_server import BaseMediaServer
from app.config import MediaServerConfig

_MEDIA_TYPE_MAP = {"movie": "movie", "episode": "episode", "audio": "track", "musicvideo": "track"}


class JellyfinBaseServer(BaseMediaServer):
    """Common Emby/Jellyfin /Sessions adapter. Subclasses override _auth_headers + type."""

    def __init__(self, cfg: MediaServerConfig):
        super().__init__(cfg)
        self.api_key = cfg.api_key

    @property
    def session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=2))
        return self._session

    def _auth_headers(self) -> Dict[str, str]:
        raise NotImplementedError

    @staticmethod
    def _is_private_ip(ip: str) -> bool:
        try:
            return ipaddress.ip_address(ip).is_private
        except ValueError:
            return False

    async def test_connection(self) -> bool:
        """Never raises. Hits /System/Info with the API key."""
        try:
            url = f"{self.url}/System/Info"
            async with self.session.get(url, headers=self._auth_headers()) as resp:
                if resp.status == 401:
                    logger.error(f"{self.type} connection test failed: invalid API key")
                    return False
                resp.raise_for_status()
                data = await resp.json()
                return bool(data.get("Id") or data.get("ServerName"))
        except Exception as e:
            logger.error(f"{self.type} connection test failed: {type(e).__name__}: {e}")
            return False

    async def get_active_streams(self) -> List[Dict[str, Any]]:
        """GET /Sessions. Raises on unreachable; [] when reachable-but-empty."""
        url = f"{self.url}/Sessions"
        async with self.session.get(url, headers=self._auth_headers()) as resp:
            if resp.status == 401:
                logger.error(f"{self.type} authentication failed - check the API key")
                return []
            resp.raise_for_status()
            sessions = await resp.json()
        out = []
        for raw in sessions or []:
            now_playing = raw.get("NowPlayingItem")
            if not now_playing:
                continue  # session with nothing playing
            out.append(self._normalize_session(raw))
        logger.debug(f"Retrieved {len(out)} active streams from {self.name}")
        return out

    def _normalize_session(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        now_playing = raw.get("NowPlayingItem") or {}
        play_state = raw.get("PlayState") or {}
        transcoding = raw.get("TranscodingInfo") or {}

        # Bitrate: prefer the video MediaStream BitRate, then NowPlayingItem.Bitrate,
        # then TranscodingInfo.Bitrate. All values are in BPS — divide by 1_000_000 to Mbps.
        bitrate_bps = 0
        for ms in now_playing.get("MediaStreams", []) or []:
            if ms.get("Type") == "Video" and ms.get("BitRate"):
                bitrate_bps = ms["BitRate"]
                break
        if not bitrate_bps:
            bitrate_bps = now_playing.get("Bitrate", 0) or transcoding.get("Bitrate", 0) or 0
        stream_bitrate_mbps = float(bitrate_bps) / 1_000_000 if bitrate_bps else 0.0

        raw_type = (now_playing.get("Type") or "").lower()
        media_type = _MEDIA_TYPE_MAP.get(raw_type, raw_type)

        remote = raw.get("RemoteEndPoint") or ""
        ip = remote.split(":")[0] if remote else ""
        is_lan = bool(raw.get("IsLocal")) or self._is_private_ip(ip)

        state = "paused" if play_state.get("IsPaused") else "playing"

        return self._finalize_stream({
            "session_key": raw.get("Id"),
            "user_name": raw.get("UserName", "Unknown"),
            "user_id": raw.get("UserId", ""),
            "media_type": media_type,
            "media_title": now_playing.get("Name"),
            "parent_title": now_playing.get("SeasonName"),
            "grandparent_title": now_playing.get("SeriesName"),
            "season_number": now_playing.get("ParentIndexNumber"),
            "episode_number": now_playing.get("IndexNumber"),
            "year": now_playing.get("ProductionYear"),
            "stream_bitrate_mbps": stream_bitrate_mbps,
            "stream_bandwidth_mbps": 0.0,  # no throughput endpoint
            "quality_profile": (now_playing.get("MediaStreams", [{}]) or [{}])[0].get("DisplayTitle"),
            "transcode_decision": "transcode" if transcoding else "direct play",
            "video_codec": transcoding.get("VideoCodec"),
            "container": now_playing.get("Container"),
            "state": state,
            "duration_seconds": (now_playing.get("RunTimeTicks", 0) or 0) / 10_000_000,
            "progress_seconds": (play_state.get("PositionTicks", 0) or 0) / 10_000_000,
            "player": raw.get("DeviceName", "Unknown"),
            "platform": raw.get("Client", "Unknown"),
            "ip_address": ip,
            "is_lan": is_lan,
        }, raw_session_id=raw.get("Id"))
