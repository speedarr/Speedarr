"""
Plex Media Server API client for monitoring streams.
"""
from typing import List, Dict, Any, Optional, Tuple
import aiohttp
import ipaddress
from xml.etree import ElementTree
from loguru import logger


class PlexClient:
    """Client for interacting with Plex Media Server API."""

    def __init__(self, url: str, token: str):
        self.url = url.rstrip("/")
        self.token = token
        self._session: Optional[aiohttp.ClientSession] = None

    @property
    def session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            # Create connector that doesn't verify SSL (many Plex servers use self-signed certs)
            connector = aiohttp.TCPConnector(ssl=False)
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=2),
                connector=connector
            )
        return self._session

    async def close(self):
        """Close the HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()

    async def test_connection(self) -> bool:
        """Test connection to Plex server."""
        url = f"{self.url}/"
        params = {"X-Plex-Token": self.token}
        headers = {"Accept": "application/json"}
        try:
            async with self.session.get(url, headers=headers, params=params) as response:
                if response.status == 401:
                    logger.error("Plex connection test failed: invalid token")
                    return False
                response.raise_for_status()
                data = await response.json()
                # Check for valid MediaContainer response
                return "MediaContainer" in data
        except aiohttp.ClientConnectorError as e:
            logger.error(f"Plex connection test failed: cannot connect to {self.url} - {e}")
            return False
        except aiohttp.ClientResponseError as e:
            logger.error(f"Plex connection test failed: HTTP {e.status} - {e.message}")
            return False
        except Exception as e:
            logger.error(f"Plex connection test failed: {type(e).__name__}: {e}")
            return False

    async def get_active_streams(self) -> List[Dict[str, Any]]:
        """
        Get list of currently active streams with real-time bandwidth.

        Combines session data from /status/sessions with actual bandwidth
        from /statistics/bandwidth.

        Connection errors propagate to the caller (polling monitor) for failure tracking.

        Returns:
            List of stream dicts containing session info, user, bitrate, bandwidth, etc.
        """
        # Fetch sessions - connection errors propagate for failure tracking
        sessions = await self._get_sessions()

        # Bandwidth stats are best-effort (may require Plex Pass)
        bandwidth_stats = await self.get_bandwidth_stats()

        if not sessions:
            return []

        active_sessions = []
        for session in sessions:
            # Log raw session data at debug level for troubleshooting
            logger.debug(f"Raw Plex session: {session.keys() if isinstance(session, dict) else type(session)}")

            # Match bandwidth stats to session by accountID + deviceID
            account_id = self._get_nested(session, "User", "id", default="")
            device_id = self._get_nested(session, "Player", "machineIdentifier", default="")

            # Look up actual bandwidth for this session
            actual_bandwidth_mbps = bandwidth_stats.get((account_id, device_id), 0.0)

            # Only include playing, buffering, or paused streams
            state = self._get_nested(session, "Player", "state", default="")
            if state in ["playing", "buffering", "paused"]:
                normalized = self._normalize_stream(session, actual_bandwidth_mbps)
                active_sessions.append(normalized)

        logger.debug(f"Retrieved {len(active_sessions)} active streams from Plex")
        return active_sessions

    async def _get_sessions(self) -> List[Dict[str, Any]]:
        """Fetch active sessions from Plex.

        Connection errors (ClientConnectorError, timeouts) propagate to caller
        for failure tracking. HTTP errors (401, 404) are handled here.
        """
        url = f"{self.url}/status/sessions"
        params = {"X-Plex-Token": self.token}
        headers = {"Accept": "application/json"}
        async with self.session.get(url, headers=headers, params=params) as response:
            # Detect redirects (e.g. HTTP→HTTPS via .plex.direct)
            if response.history:
                logger.warning(f"Plex redirected: {url} -> {response.url.origin()}{response.url.path}")
            if response.status == 401:
                logger.error("Plex authentication failed - check your X-Plex-Token")
                return []
            if response.status == 404:
                logger.error(f"Plex sessions endpoint not found at {response.url}")
                return []
            response.raise_for_status()
            data = await response.json()
            container = data.get("MediaContainer", {})

            # Log the structure for debugging
            sessions = container.get("Metadata", [])
            if sessions:
                # Log first session structure for debugging
                first_session = sessions[0]
                logger.debug(f"Plex session keys: {list(first_session.keys())}")
                if "Media" in first_session and first_session["Media"]:
                    logger.debug(f"Media[0] keys: {list(first_session['Media'][0].keys())}")
                    logger.debug(f"Media[0].bitrate: {first_session['Media'][0].get('bitrate')}")
                if "Session" in first_session:
                    logger.debug(f"Session keys: {list(first_session['Session'].keys())}")
                    logger.debug(f"Session.bandwidth: {first_session['Session'].get('bandwidth')}")

            return sessions

    async def get_bandwidth_stats(self) -> Dict[Tuple[str, str], float]:
        """
        Get real-time bandwidth per account/device from Plex.

        Note: This endpoint may require Plex Pass. If unavailable, returns empty dict
        and the system will fall back to using session bitrate data.

        Returns:
            Dict mapping (accountID, deviceID) to bandwidth in Mbps
        """
        url = f"{self.url}/statistics/bandwidth"
        params = {"X-Plex-Token": self.token, "timespan": 4}

        try:
            async with self.session.get(url, params=params) as response:
                if response.status == 401:
                    logger.warning("Plex bandwidth stats: authentication failed")
                    return {}
                if response.status == 404:
                    # This endpoint may not exist on all Plex versions or without Plex Pass
                    logger.debug("Plex bandwidth stats endpoint not available (may require Plex Pass)")
                    return {}
                response.raise_for_status()
                # This endpoint returns XML
                xml_text = await response.text()
                return self._parse_bandwidth_xml(xml_text)

        except aiohttp.ClientConnectorError as e:
            logger.error(f"Failed to connect to Plex for bandwidth stats: {e}")
            return {}
        except aiohttp.ClientResponseError as e:
            logger.warning(f"Plex bandwidth stats request failed: HTTP {e.status} - {e.message}")
            return {}
        except Exception as e:
            logger.warning(f"Failed to fetch bandwidth stats: {type(e).__name__}: {e}")
            return {}

    def _parse_bandwidth_xml(self, xml_text: str) -> Dict[Tuple[str, str], float]:
        """
        Parse bandwidth XML response and calculate Mbps for each account/device.

        XML format:
        <MediaContainer>
            <StatisticsBandwidth accountID="123" deviceID="456" timespan="6" bytes="10000000" .../>
        </MediaContainer>
        """
        result: Dict[Tuple[str, str], float] = {}

        try:
            root = ElementTree.fromstring(xml_text)
            for stat in root.findall(".//StatisticsBandwidth"):
                account_id = stat.get("accountID", "")
                device_id = stat.get("deviceID", "")
                timespan = int(stat.get("timespan", "6"))
                bytes_transferred = int(stat.get("bytes", "0"))

                # Calculate Mbps: (bytes / timespan) * 8 / 1_000_000
                if timespan > 0:
                    mbps = (bytes_transferred / timespan) * 8 / 1_000_000
                    result[(account_id, device_id)] = mbps

        except ElementTree.ParseError as e:
            logger.error(f"Failed to parse bandwidth XML: {e}")

        return result

    def _normalize_stream(self, session: Dict[str, Any], actual_bandwidth_mbps: float) -> Dict[str, Any]:
        """
        Normalize Plex session data to Speedarr format.

        Args:
            session: Raw Plex session data
            actual_bandwidth_mbps: Real-time bandwidth from /statistics/bandwidth

        Returns:
            Normalized stream dict with both bitrate and bandwidth metrics
        """
        # Get media info (first media item)
        media = session.get("Media", [{}])[0] if session.get("Media") else {}

        # Get transcode session info if transcoding
        transcode = session.get("TranscodeSession", {})

        # Get session info
        session_info = session.get("Session", {})

        # Calculate media bitrate - try multiple sources (all in kbps)
        # 1. Session.bandwidth - reported bandwidth for this session
        # 2. Media.bitrate - file's overall bitrate
        # 3. TranscodeSession.speed * Media.bitrate - if transcoding
        bitrate_kbps = session_info.get("bandwidth", 0)
        if not bitrate_kbps:
            # Fall back to media bitrate
            bitrate_kbps = media.get("bitrate", 0)
        if not bitrate_kbps and transcode:
            # If transcoding, try to get from transcode session
            bitrate_kbps = transcode.get("bitrate", 0)

        stream_bitrate_mbps = float(bitrate_kbps) / 1000 if bitrate_kbps else 0.0

        # Log for debugging if bitrate is 0
        if stream_bitrate_mbps == 0:
            logger.debug(f"Zero bitrate for session - Session.bandwidth: {session_info.get('bandwidth')}, "
                        f"Media.bitrate: {media.get('bitrate')}, TranscodeSession: {transcode.get('bitrate') if transcode else 'N/A'}")

        # Get IP address from location or player address
        # Note: Plex sometimes returns literal "lan" or "wan" for location instead of IP
        location = session_info.get("location", "")
        player_address = self._get_nested(session, "Player", "address", default="")

        # Prefer location if it's a valid IP, otherwise use player address
        ip_address = location if self._is_valid_ip(location) else player_address

        # Determine LAN status - use Plex's local field, "lan" location, OR check if IP is private
        plex_says_local = session_info.get("local") == "1" or session_info.get("local") is True
        location_says_lan = location.lower() == "lan"  # Plex sometimes uses literal "lan"/"wan"
        ip_is_private = self._is_private_ip(ip_address)
        is_lan = plex_says_local or location_says_lan or ip_is_private

        # Debug logging for LAN detection
        user_name = self._get_nested(session, "User", "title", default="Unknown")
        logger.debug(f"LAN detection for {user_name}: ip='{ip_address}', "
                     f"plex_local={plex_says_local}, location_lan={location_says_lan}, "
                     f"ip_private={ip_is_private}, is_lan={is_lan}")

        return {
            "session_id": session_info.get("id"),
            "session_key": session.get("sessionKey"),
            "user_name": self._get_nested(session, "User", "title", default="Unknown"),
            "user_id": self._get_nested(session, "User", "id", default=""),
            "media_type": session.get("type"),
            "media_title": session.get("title"),
            "parent_title": session.get("parentTitle"),
            "grandparent_title": session.get("grandparentTitle"),
            "season_number": session.get("parentIndex"),
            "episode_number": session.get("index"),
            "year": session.get("year"),
            # Two SEPARATE metrics - no fallback relationship
            "stream_bitrate_mbps": stream_bitrate_mbps,  # Media file bitrate from session
            "stream_bandwidth_mbps": actual_bandwidth_mbps,  # Actual network throughput
            "quality_profile": media.get("videoResolution"),
            "transcode_decision": transcode.get("videoDecision", "direct play") if transcode else "direct play",
            "video_codec": media.get("videoCodec"),
            "container": media.get("container"),
            "state": self._get_nested(session, "Player", "state", default="unknown"),
            "duration_seconds": session.get("duration", 0) / 1000 if session.get("duration") else 0,
            "progress_seconds": session.get("viewOffset", 0) / 1000 if session.get("viewOffset") else 0,
            "player": self._get_nested(session, "Player", "title", default="Unknown"),
            "platform": self._get_nested(session, "Player", "platform", default="Unknown"),
            "ip_address": ip_address,
            "is_lan": is_lan,
        }

    @staticmethod
    def _get_nested(data: Dict, *keys: str, default: Any = None) -> Any:
        """Safely get nested dictionary value."""
        for key in keys:
            if isinstance(data, dict):
                data = data.get(key, default)
            else:
                return default
        return data

    @staticmethod
    def _is_valid_ip(ip_str: str) -> bool:
        """Check if a string is a valid IP address."""
        if not ip_str:
            return False
        try:
            ipaddress.ip_address(ip_str)
            return True
        except ValueError:
            return False

    @staticmethod
    def _is_private_ip(ip_str: str) -> bool:
        """Check if an IP address is private/local."""
        if not ip_str:
            return False
        try:
            ip = ipaddress.ip_address(ip_str)
            return ip.is_private or ip.is_loopback
        except ValueError:
            # Invalid IP address format
            return False
