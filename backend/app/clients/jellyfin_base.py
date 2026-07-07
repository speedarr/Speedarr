"""
Shared base for Emby and Jellyfin (Jellyfin is a fork of Emby).

Both expose GET /Sessions returning a JSON array of sessions with
NowPlayingItem / PlayState / TranscodingInfo / RemoteEndPoint / UserName.
Bitrates are in BPS (not kbps). There is no /statistics/bandwidth equivalent,
so stream_bandwidth_mbps is always 0.
"""
from typing import Any, Dict, List

import aiohttp
from loguru import logger

from app.clients.base_media_server import BaseMediaServer
from app.config import MediaServerConfig
from app.utils.network import classify_lan, is_private_ip
from app.utils.quality import resolution_from_display_title

_MEDIA_TYPE_MAP = {"movie": "movie", "episode": "episode", "audio": "track", "musicvideo": "track"}


class JellyfinBaseServer(BaseMediaServer):
    """Common Emby/Jellyfin /Sessions adapter. Subclasses override _auth_headers + type."""

    # Server config endpoint exposing LocalNetworkSubnets. Set by subclasses.
    _network_config_path: str = ""

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
    def _host_from_endpoint(endpoint: str) -> str:
        ep = (endpoint or "").strip()
        if not ep:
            return ""
        if ep.startswith("["):            # [ipv6] or [ipv6]:port
            return ep[1:ep.index("]")] if "]" in ep else ep[1:]
        if ep.count(":") == 1:            # ipv4:port
            return ep.split(":")[0]
        return ep                          # bare ipv4 or bare ipv6 (multiple colons)

    @staticmethod
    def _parse_network_config(data: Dict[str, Any]) -> List[str]:
        """Extract LAN subnets from a /System/Configuration[/network] payload.

        Only LocalNetworkSubnets is used: it is the server's authoritative LAN
        definition and the sole field needed for classification. LocalNetworkAddresses
        is intentionally ignored — it is version-inconsistent (bare IPs vs full URLs)
        and empty on the servers we target.
        """
        if not isinstance(data, dict):
            return []
        out: List[str] = []
        for entry in data.get("LocalNetworkSubnets") or []:
            if isinstance(entry, str) and entry.strip():
                out.append(entry.strip())
        return out

    async def refresh_lan_subnets(self) -> None:
        """Read LocalNetworkSubnets from the server config API and cache it.

        Never raises. On any failure the previous cache (or empty list) is kept,
        and classification falls back to the private-IP heuristic.
        """
        if not self._network_config_path:
            return
        url = f"{self.url}{self._network_config_path}"
        try:
            async with self.session.get(url, headers=self._auth_headers()) as resp:
                if resp.status != 200:
                    logger.warning(
                        f"{self.type} '{self.name}': cannot read network config "
                        f"(HTTP {resp.status}); keeping "
                        f"{'cached subnets' if self._auto_subnets else 'private-IP fallback'}"
                    )
                    return
                data = await resp.json(content_type=None)
        except Exception as e:
            logger.warning(f"{self.type} '{self.name}': network config read failed: "
                           f"{type(e).__name__}: {e}")
            return
        self._auto_subnets = self._parse_network_config(data)
        logger.info(f"{self.type} '{self.name}': LAN subnets = "
                    f"{self._auto_subnets or '(none; using private-IP fallback)'}")

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
        video_ms = next((ms for ms in now_playing.get("MediaStreams", []) or []
                         if ms.get("Type") == "Video"), {})
        bitrate_bps = video_ms.get("BitRate") or now_playing.get("Bitrate", 0) \
            or transcoding.get("Bitrate", 0) or 0
        stream_bitrate_mbps = float(bitrate_bps) / 1_000_000 if bitrate_bps else 0.0

        raw_type = (now_playing.get("Type") or "").lower()
        media_type = _MEDIA_TYPE_MAP.get(raw_type, raw_type)

        remote = raw.get("RemoteEndPoint") or ""
        ip = self._host_from_endpoint(remote)
        # Precedence: manual override -> auto-read subnets -> private-IP fallback.
        # A server-provided IsLocal flag (rare for Emby/Jellyfin) is honored on top.
        if self.lan_networks:
            ip_is_lan = classify_lan(ip, self.lan_networks)
        elif self._auto_subnets:
            ip_is_lan = classify_lan(ip, self._auto_subnets)
        else:
            ip_is_lan = is_private_ip(ip)
        is_lan = bool(raw.get("IsLocal")) or ip_is_lan

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
            "quality_profile": resolution_from_display_title(video_ms.get("DisplayTitle")),
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
