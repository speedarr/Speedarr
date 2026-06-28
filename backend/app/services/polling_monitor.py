"""
Polling monitor service for stream detection and client monitoring.
"""
import asyncio
import json
from typing import Dict, Any, List, Optional, Callable, Tuple
from datetime import datetime, timedelta, timezone
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from app.clients.plex import PlexClient
from app.clients.base_media_server import BaseMediaServer
from app.config import SpeedarrConfig
from app.services.decision_engine import DecisionEngine
from app.services.controller_manager import ControllerManager
from app.models import BandwidthMetric, ThrottleDecision
from app.utils.bandwidth import calculate_stream_bandwidth, filter_streams_for_bandwidth
from app.utils.formatting import format_display_title

# Import TYPE_CHECKING to avoid circular imports
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from app.services.notification_service import NotificationService


def aggregate_per_server_bandwidth(streams: List[Dict[str, Any]]) -> Dict[str, float]:
    """Sum in-use stream bitrate (Mbps) per server_id for the per_server metric."""
    totals: Dict[str, float] = {}
    for s in streams:
        sid = s.get("server_id")
        if not sid:
            continue
        totals[sid] = totals.get(sid, 0.0) + (s.get("stream_bitrate_mbps", 0) or 0)
    return totals


def build_per_client_metrics(download_stats: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Build the per_client metric map keyed by client id.

    Returns {client_id: {"d": dl_speed, "u": ul_speed, "dl": dl_limit, "ul": ul_limit}}.
    Values are taken verbatim from each client's stats (may be None).
    """
    result: Dict[str, Dict[str, Any]] = {}
    for cid, stats in download_stats.items():
        result[cid] = {
            "d": stats.get("download_speed"),
            "u": stats.get("upload_speed"),
            "dl": stats.get("download_limit"),
            "ul": stats.get("upload_limit"),
        }
    return result


def build_decision_per_client(old_stats: dict, new_stats: dict, direction: str) -> dict:
    """Per-client-id limit changes for a throttle decision.

    direction is 'download' or 'upload'. Returns {client_id: {name, type,
    old_<direction>_limit, new_<direction>_limit}} for every client whose
    <direction>_limit changed (old and new both present and different).
    """
    limit_key = f"{direction}_limit"
    old_field, new_field = f"old_{direction}_limit", f"new_{direction}_limit"
    result = {}
    for cid in set(old_stats) | set(new_stats):
        o = old_stats.get(cid) or {}
        n = new_stats.get(cid) or {}
        old_v = o.get(limit_key)
        new_v = n.get(limit_key)
        if old_v is not None and new_v is not None and old_v != new_v:
            meta = n if n else o
            result[cid] = {
                "name": meta.get("client_name", cid),
                "type": meta.get("client_type"),
                old_field: old_v,
                new_field: new_v,
            }
    return result


def sum_stat_by_type(
    download_stats: Dict[str, Dict[str, Any]], client_type: str, stat_key: str
) -> Optional[float]:
    """Sum a stat across all clients of one type for the legacy per-type columns.

    Returns None when no client of that type reports a non-None value, so the
    legacy column stays NULL exactly as it did before any client of the type existed.
    """
    values = [
        s.get(stat_key)
        for s in download_stats.values()
        if s.get("client_type") == client_type and s.get(stat_key) is not None
    ]
    if not values:
        return None
    return sum(values)


class PollingMonitor:
    """
    Polling-based monitoring service for Plex streams and download clients.
    Queries Plex and download clients periodically.
    """

    def __init__(
        self,
        config: SpeedarrConfig,
        decision_engine: DecisionEngine,
        controller_manager: ControllerManager,
        get_db_session: Optional[Callable[[], AsyncSession]] = None,
        notification_service: Optional["NotificationService"] = None
    ):
        self.config = config
        self.decision_engine = decision_engine
        self.controller_manager = controller_manager
        self._get_db_session = get_db_session
        self.notification_service = notification_service

        # Initialize media servers (one adapter per enabled server)
        from app.clients.media_server_factory import create_media_server
        self.media_servers: Dict[str, BaseMediaServer] = {
            s.id: create_media_server(s) for s in self.config.get_enabled_media_servers()
        }
        self._server_state: Dict[str, Dict[str, Any]] = {
            sid: {"failures": 0, "warned": False, "last_streams": [], "last_success": None}
            for sid in self.media_servers
        }

        # Initialize SNMP monitor if enabled
        self.snmp_monitor = None
        if self.config.snmp.enabled:
            from app.services.snmp_monitor import SNMPMonitor
            self.snmp_monitor = SNMPMonitor(self.config.snmp)
            logger.info(f"SNMP monitor initialized for interface: {self.config.snmp.interface}")
        else:
            logger.info("SNMP monitoring disabled")

        self._running = False
        self._download_task: Optional[asyncio.Task] = None
        self._plex_task: Optional[asyncio.Task] = None
        self._cached_streams: List[Dict[str, Any]] = []
        self._restoration_scheduled_at: Optional[datetime] = None
        # Track bandwidth per session for accurate reservation
        # Format: {session_id: {"bandwidth": float, "timestamp": datetime}}
        self._session_bandwidth: Dict[str, Dict[str, Any]] = {}
        self._session_bandwidth_max_size = 1000  # Prevent unbounded growth
        self._session_bandwidth_max_age_seconds = 3600  # Clean up entries older than 1 hour
        self._reservations: List[Dict[str, Any]] = []  # Track multiple independent reservations
        self._last_snmp_data: Optional[Dict[str, float]] = None  # Last SNMP readings for status API
        self._cached_client_stats: Dict[str, Dict[str, Any]] = {}  # Last client stats for status API
        self._temporary_limits: Optional[Dict[str, Any]] = None  # Temporary bandwidth limit overrides
        self._first_poll: bool = True  # Flag to skip notifications on first poll (startup)

        # Plex failsafe tracking
        # Maximum consecutive failures before considering Plex truly down
        self._plex_max_failures: int = 6  # ~30 seconds at 5-second polling

        # Download client unreachable tracking
        self._client_unreachable_counts: Dict[str, int] = {}  # client_id -> consecutive failures
        self._client_unreachable_warned: Dict[str, bool] = {}  # client_id -> already notified

        # SNMP unreachable tracking
        self._snmp_consecutive_failures: int = 0
        self._snmp_unreachable_warned: bool = False

        # Locks for thread-safe access to shared state
        self._streams_lock = asyncio.Lock()
        self._reservations_lock = asyncio.Lock()
        self._session_bandwidth_lock = asyncio.Lock()
        self._temporary_limits_lock = asyncio.Lock()

    async def start(self):
        """Start the polling monitor with separate download and Plex cycles."""
        self._running = True
        # Start download monitoring
        self._download_task = asyncio.create_task(self._download_poll_loop())
        # Start Plex monitoring
        self._plex_task = asyncio.create_task(self._plex_poll_loop())
        logger.info("Polling monitor started (download + Plex cycles)")

    async def stop(self):
        """Stop the polling monitor."""
        self._running = False
        if self._download_task:
            self._download_task.cancel()
            try:
                await self._download_task
            except asyncio.CancelledError:
                pass
        if self._plex_task:
            self._plex_task.cancel()
            try:
                await self._plex_task
            except asyncio.CancelledError:
                pass
        # Cancel all reservation tasks (use lock for thread-safe access)
        async with self._reservations_lock:
            for reservation in self._reservations:
                if reservation.get('task'):
                    reservation['task'].cancel()
                    try:
                        await reservation['task']
                    except asyncio.CancelledError:
                        pass
        for server in self.media_servers.values():
            await server.close()
        logger.info("Polling monitor stopped")

    async def store_session_bandwidth(self, session_id: str, bandwidth_mbps: float):
        """Store bandwidth for a session (used when stream starts)."""
        async with self._session_bandwidth_lock:
            # Clean up stale entries and enforce max size
            await self._cleanup_session_bandwidth_unlocked()

            self._session_bandwidth[session_id] = {
                "bandwidth": bandwidth_mbps,
                "timestamp": datetime.now(timezone.utc)
            }
        logger.debug(f"Stored bandwidth {bandwidth_mbps:.1f} Mbps for session {session_id}")

    async def get_session_bandwidth(self, session_id: str) -> Optional[float]:
        """Get stored bandwidth for a session (used when stream stops)."""
        async with self._session_bandwidth_lock:
            entry = self._session_bandwidth.get(session_id)
            return entry["bandwidth"] if entry else None

    async def clear_session_bandwidth(self, session_id: str):
        """Clear bandwidth for a session after reservation is scheduled."""
        async with self._session_bandwidth_lock:
            entry = self._session_bandwidth.pop(session_id, None)
        if entry:
            logger.debug(f"Cleared stored bandwidth {entry['bandwidth']:.1f} Mbps for session {session_id}")

    async def _cleanup_session_bandwidth_unlocked(self):
        """
        Clean up stale session bandwidth entries.
        Must be called while holding _session_bandwidth_lock.
        """
        now = datetime.now(timezone.utc)
        stale_sessions = [
            session_id for session_id, entry in self._session_bandwidth.items()
            if (now - entry["timestamp"]).total_seconds() > self._session_bandwidth_max_age_seconds
        ]

        for session_id in stale_sessions:
            entry = self._session_bandwidth.pop(session_id)
            logger.debug(f"Cleaned up stale session bandwidth entry: {session_id} ({entry['bandwidth']:.1f} Mbps)")

        # Enforce max size by removing oldest entries
        if len(self._session_bandwidth) > self._session_bandwidth_max_size:
            sorted_sessions = sorted(
                self._session_bandwidth.items(),
                key=lambda x: x[1]["timestamp"]
            )
            # Remove oldest entries to get back under limit
            excess = len(self._session_bandwidth) - self._session_bandwidth_max_size
            for session_id, entry in sorted_sessions[:excess]:
                self._session_bandwidth.pop(session_id)
                logger.warning(f"Evicted session bandwidth entry due to size limit: {session_id}")

    async def schedule_restoration(self, delay_seconds: int, bandwidth_to_restore_mbps: float, user_id: str = None, player: str = None, user_name: str = None, media_title: str = None):
        """
        Schedule an independent bandwidth reservation with its own timer.

        Args:
            delay_seconds: Duration to reserve bandwidth (seconds)
            bandwidth_to_restore_mbps: Amount of bandwidth freed up by stream ending (Mbps)
            user_id: User ID who ended the stream
            player: Player/client name that ended the stream
            user_name: User name who ended the stream
            media_title: Title of the media that ended
        """
        if delay_seconds <= 0:
            logger.debug("Restoration delay is 0, skipping reservation")
            return

        # Create unique reservation ID
        timestamp = datetime.now(timezone.utc).isoformat()
        reservation_id = f"{user_id}_{player}_{timestamp}"

        # Create reservation object
        now_utc = datetime.now(timezone.utc)
        reservation = {
            'id': reservation_id,
            'bandwidth_mbps': bandwidth_to_restore_mbps,
            'user_id': user_id,
            'player': player,
            'user_name': user_name,
            'media_title': media_title,
            'start_time': now_utc,
            'duration_seconds': delay_seconds,
            'expires_at': now_utc + timedelta(seconds=delay_seconds),
            'task': None  # Will be set below
        }

        # Create independent cleanup task for this specific reservation
        reservation['task'] = asyncio.create_task(
            self._clear_specific_reservation(reservation_id, delay_seconds)
        )

        # Add to reservations list with lock
        async with self._reservations_lock:
            self._reservations.append(reservation)

        logger.info(f"Bandwidth reservation: {bandwidth_to_restore_mbps:.1f} Mbps for {delay_seconds}s ({delay_seconds//60}min {delay_seconds%60}s) (user: {user_id}, player: {player})")

    async def get_total_reserved_bandwidth(self) -> float:
        """Calculate total bandwidth across all active reservations."""
        async with self._reservations_lock:
            return sum(res['bandwidth_mbps'] for res in self._reservations)

    async def should_cancel_reservation(self, user_id: str = None, player: str = None) -> bool:
        """
        Check if reservation should be cancelled for this user/player combination.

        Args:
            user_id: User ID starting the stream
            player: Player/client name starting the stream

        Returns:
            True if reservation should be cancelled, False otherwise
        """
        if not user_id or not player:
            return False

        # Check if ANY reservation matches this user AND player
        async with self._reservations_lock:
            for reservation in self._reservations:
                same_user = (str(user_id) == str(reservation['user_id'])) if user_id and reservation['user_id'] else False
                same_player = (str(player) == str(reservation['player'])) if player and reservation['player'] else False

                if same_user and same_player:
                    logger.info(f"Same user ({user_id}) resuming on same player ({player}) - cancelling their reservation")
                    return True

        logger.debug(f"Different user/player - keeping all reservations")
        return False

    async def cancel_restoration(self, user_id: str = None, player: str = None):
        """Cancel reservation for specific user/player if they resume watching."""

        # Find and cancel matching reservation(s)
        cancelled_bandwidth = 0.0
        remaining_reservations = []

        async with self._reservations_lock:
            for reservation in self._reservations:
                same_user = (str(user_id) == str(reservation['user_id'])) if user_id and reservation['user_id'] else False
                same_player = (str(player) == str(reservation['player'])) if player and reservation['player'] else False

                if same_user and same_player:
                    # Cancel this reservation's timer
                    if reservation['task']:
                        reservation['task'].cancel()
                    cancelled_bandwidth += reservation['bandwidth_mbps']
                    logger.info(f"Cancelled reservation for user {user_id}: {reservation['bandwidth_mbps']:.1f} Mbps")
                else:
                    # Keep this reservation
                    remaining_reservations.append(reservation)

            self._reservations = remaining_reservations
            total_remaining = sum(res['bandwidth_mbps'] for res in self._reservations)

        if cancelled_bandwidth > 0:
            logger.info(f"Total cancelled: {cancelled_bandwidth:.1f} Mbps, Total remaining reserved: {total_remaining:.1f} Mbps")

    async def clear_reservation_by_id(self, reservation_id: str) -> bool:
        """
        Clear a specific reservation by its ID.

        Args:
            reservation_id: The unique ID of the reservation to clear

        Returns:
            True if reservation was found and cleared, False otherwise
        """
        async with self._reservations_lock:
            for idx, reservation in enumerate(self._reservations):
                if reservation['id'] == reservation_id:
                    # Cancel the timer task
                    if reservation['task']:
                        reservation['task'].cancel()

                    # Remove from list
                    cleared = self._reservations.pop(idx)
                    logger.info(f"Manually cleared reservation {reservation_id}: {cleared['bandwidth_mbps']:.1f} Mbps (user: {cleared.get('user_name', 'Unknown')})")
                    return True

        logger.warning(f"Reservation {reservation_id} not found")
        return False

    async def get_reservations(self) -> List[Dict[str, Any]]:
        """
        Get list of active reservations for API.

        Returns:
            List of reservation dicts (without task objects)
        """
        async with self._reservations_lock:
            return [
                {
                    'id': res['id'],
                    'bandwidth_mbps': res['bandwidth_mbps'],
                    'user_id': res['user_id'],
                    'player': res['player'],
                    'user_name': res['user_name'],
                    'media_title': res['media_title'],
                    'start_time': res['start_time'].isoformat() if res['start_time'] else None,
                    'duration_seconds': res['duration_seconds'],
                    'expires_at': res['expires_at'].isoformat() if res['expires_at'] else None,
                }
                for res in self._reservations
            ]

    async def get_reserved_download_bandwidth(self) -> float:
        """
        Calculate download bandwidth reserve from held (ended) stream reservations.
        This is a derived value from the existing upload reservations - as upload holds expire,
        the download reserve automatically decreases.

        Returns:
            Download bandwidth to reserve in Mbps
        """
        pct = self.config.bandwidth.streams.download_reserve_percent
        if pct <= 0:
            return 0.0
        total_upload_held = await self.get_total_reserved_bandwidth()
        return total_upload_held * (pct / 100)

    async def get_reserved_bandwidth(self) -> float:
        """
        Calculate how much bandwidth is currently reserved (not available for allocation).
        Returns the sum of all active reservations (binary reservation per stream).

        Returns:
            Reserved bandwidth in Mbps (sum of all active reservations)
        """
        # Use the helper method that sums all reservation bandwidth
        total = await self.get_total_reserved_bandwidth()

        if total > 0:
            async with self._reservations_lock:
                count = len(self._reservations)
            logger.debug(f"Total reserved bandwidth: {total:.1f} Mbps across {count} reservation(s)")

        return total

    async def get_active_temporary_limits(self) -> tuple[Optional[float], Optional[float]]:
        """
        Get active temporary bandwidth limits if they haven't expired.

        Returns:
            Tuple of (download_mbps, upload_mbps), both None if no active limits
        """
        async with self._temporary_limits_lock:
            if not self._temporary_limits:
                return None, None

            expires_at = self._temporary_limits.get('expires_at')

            if expires_at is None:
                # Indefinite limit — active until explicitly cleared
                return (
                    self._temporary_limits.get('download_mbps'),
                    self._temporary_limits.get('upload_mbps')
                )

            if datetime.now(timezone.utc) > expires_at:
                # Expired - clear and return None
                logger.info("Temporary bandwidth limits expired, reverting to normal limits")
                self._temporary_limits = None
                return None, None

            return (
                self._temporary_limits.get('download_mbps'),
                self._temporary_limits.get('upload_mbps')
            )

    async def _clear_specific_reservation(self, reservation_id: str, delay_seconds: int):
        """Wait for reservation period, then clear ONLY this specific reservation."""
        try:
            await asyncio.sleep(delay_seconds)

            # Find and remove ONLY this reservation
            reservation = None
            async with self._reservations_lock:
                for idx, res in enumerate(self._reservations):
                    if res['id'] == reservation_id:
                        reservation = self._reservations.pop(idx)
                        break
                total_remaining = sum(r['bandwidth_mbps'] for r in self._reservations)

            if reservation:
                logger.info(f"Reservation expired for user {reservation['user_id']}, clearing {reservation['bandwidth_mbps']:.1f} Mbps (total remaining: {total_remaining:.1f} Mbps)")
            else:
                logger.warning(f"Reservation {reservation_id} not found (may have been cancelled)")

        except asyncio.CancelledError:
            logger.debug(f"Reservation {reservation_id} was cancelled")
            raise
        except Exception as e:
            logger.error(f"Error in reservation cleanup for {reservation_id}: {e}")

    async def _poll_one(self, server: "BaseMediaServer") -> Tuple[bool, List[Dict[str, Any]]]:
        """
        Poll one media server. Never raises.

        Returns (reachable_this_cycle, effective_streams). On success, records
        last_streams. On failure, holds last_streams within the grace period,
        then drops to []. Tags each stream with the server's LAN policy.
        """
        state = self._server_state[server.server_id]
        try:
            streams = await server.get_active_streams()
            for s in streams:
                s["include_lan_streams"] = server.include_lan_streams
            state["failures"] = 0
            state["last_streams"] = streams
            state["last_success"] = datetime.now(timezone.utc)
            if state["warned"]:
                logger.info(f"Media server '{server.name}' connection restored")
                state["warned"] = False
                if self.notification_service:
                    await self.notification_service.notify(
                        "service_unreachable",
                        f"Media server '{server.name}' is back online.",
                        {"service": server.name, "server_id": server.server_id, "status": "recovered"},
                    )
            return True, streams
        except Exception as err:
            state["failures"] += 1
            grace = self.config.failsafe.server_hold_grace_seconds
            last_success = state["last_success"]
            within_grace = (
                last_success is not None
                and (datetime.now(timezone.utc) - last_success).total_seconds() < grace
            )
            held = state["last_streams"] if within_grace else []
            if state["failures"] > self._plex_max_failures and not state["warned"]:
                logger.error(f"Media server '{server.name}' unreachable for {state['failures']} polls: {err}")
                state["warned"] = True
                if self.notification_service:
                    await self.notification_service.notify(
                        "service_unreachable",
                        f"Media server '{server.name}' is unreachable. Bandwidth limits maintained.",
                        {"service": server.name, "server_id": server.server_id,
                         "status": "unreachable", "consecutive_failures": state["failures"]},
                    )
            return False, [dict(s) for s in held]

    async def _plex_poll_loop(self):
        """Plex stream monitoring loop."""
        while self._running:
            try:
                await self._plex_poll_cycle()
            except Exception as e:
                logger.error(f"Error in media server polling cycle: {e}")

            await asyncio.sleep(self.config.system.update_frequency)

    async def _plex_poll_cycle(self):
        """Check Plex streams and cache them."""
        try:
            # Store old streams before fetching new ones (for detecting stopped streams)
            old_streams = self._cached_streams.copy()
            old_session_ids = {s.get("session_id") for s in old_streams if s.get("session_id")}

            # Poll every server in parallel; _poll_one never raises.
            if self.media_servers:
                results = await asyncio.gather(
                    *[self._poll_one(s) for s in self.media_servers.values()]
                )
            else:
                results = []
            any_reachable = any(reachable for reachable, _ in results)
            merged = [s for _, streams in results for s in streams]

            # TOTAL OUTAGE: no server reachable this cycle -> maintain current
            # limits (do NOT recompute or restore). Per-server failure counts
            # live in self._server_state.
            if self.media_servers and not any_reachable:
                return

            new_streams = merged
            self._cached_streams = new_streams

            new_session_ids = {s.get("session_id") for s in self._cached_streams if s.get("session_id")}

            logger.debug(f"Plex: {len(self._cached_streams)} active streams")

            # On first poll (startup), don't send notifications for existing streams
            if self._first_poll:
                logger.info(f"First poll: found {len(self._cached_streams)} existing streams (not sending notifications)")
                self._first_poll = False
                # Initialize notification service state without sending notifications
                if self.notification_service:
                    total_bandwidth = sum(
                        s.get("stream_bandwidth_mbps", 0) or s.get("stream_bitrate_mbps", 0)
                        for s in self._cached_streams
                    )
                    stream_count = len(self._cached_streams)
                    self.notification_service.initialize_state(stream_count, total_bandwidth)
                return  # Skip detecting started/stopped streams on first poll

            # Detect streams that stopped (were in old but not in new)
            stopped_session_ids = old_session_ids - new_session_ids

            if stopped_session_ids:
                logger.info(f"Detected {len(stopped_session_ids)} stream(s) stopped via polling (no webhook received)")

                # Process each stopped stream
                for session_id in stopped_session_ids:
                    # Find the stream data from old cache
                    stopped_stream = next(
                        (s for s in old_streams if s.get("session_id") == session_id),
                        None
                    )

                    if stopped_stream:
                        await self._handle_stopped_stream(stopped_stream)

            # Detect streams that started (in new but not in old)
            started_session_ids = new_session_ids - old_session_ids

            if started_session_ids:
                logger.info(f"Detected {len(started_session_ids)} new stream(s) started")
                for session_id in started_session_ids:
                    new_stream = next(
                        (s for s in self._cached_streams if s.get("session_id") == session_id),
                        None
                    )
                    if new_stream:
                        user_id = new_stream.get("user_id")
                        player = new_stream.get("player")
                        # Cancel any existing reservation for this user/player combo
                        if user_id and player:
                            await self.cancel_restoration(user_id=user_id, player=player)

                        # Send stream_started notification
                        if self.notification_service:
                            # Calculate totals for the notification message
                            total_bandwidth = sum(
                                s.get("stream_bandwidth_mbps", 0) or s.get("stream_bitrate_mbps", 0)
                                for s in self._cached_streams
                            )
                            stream_count = len(self._cached_streams)
                            stream_bitrate = new_stream.get("stream_bandwidth_mbps", 0) or new_stream.get("stream_bitrate_mbps", 0)
                            user_name = new_stream.get('user_name', 'Unknown')
                            display_title = format_display_title(new_stream)

                            await self.notification_service.notify(
                                "stream_started",
                                f"Stream started: ({stream_bitrate:.1f} Mbps) | Total: {total_bandwidth:.1f} Mbps ({stream_count} stream{'s' if stream_count != 1 else ''}) | {user_name} watching {display_title}",
                                {
                                    "session_id": session_id,
                                    "user_name": user_name,
                                    "user_id": user_id,
                                    "media_title": display_title,
                                    "player": player,
                                    "stream_bitrate_mbps": stream_bitrate,
                                    "total_bandwidth_mbps": total_bandwidth,
                                    "stream_count": stream_count,
                                    "quality_profile": new_stream.get("quality_profile"),
                                    "is_lan": new_stream.get("is_lan"),
                                }
                            )

            # Check stream count and bitrate thresholds for notifications
            # Filter by LAN/WAN to match the streams the decision engine manages
            if self.notification_service:
                threshold_streams = filter_streams_for_bandwidth(self._cached_streams)
                # Use stream_bandwidth_mbps (real-time) with fallback to stream_bitrate_mbps (media file bitrate)
                total_bandwidth = sum(
                    s.get("stream_bandwidth_mbps", 0) or s.get("stream_bitrate_mbps", 0)
                    for s in threshold_streams
                )
                stream_count = len(threshold_streams)
                await self.notification_service.check_stream_count_threshold(stream_count, total_bandwidth)
                await self.notification_service.check_stream_bitrate_threshold(total_bandwidth, stream_count)

        except Exception as e:
            logger.error(f"Error in media server poll cycle: {e}")

    async def _handle_stopped_stream(self, stream: Dict[str, Any]):
        """
        Handle a stream that stopped.
        Schedules bandwidth holding and sends notifications.
        """
        try:
            session_id = stream.get("session_id")
            user_id = stream.get("user_id")
            user_name = stream.get("user_name")
            player = stream.get("player")
            media_title = stream.get("media_title")
            display_title = format_display_title(stream)
            media_type = stream.get("media_type")
            is_lan = stream.get("is_lan", False)

            # Skip holding bandwidth for LAN streams if this server's policy excludes them
            if not stream.get("include_lan_streams", False) and is_lan:
                logger.debug(f"Skipping bandwidth hold for LAN stream: {user_name} - {display_title}")
                # Still send notification but don't hold bandwidth
                if self.notification_service:
                    await self.notification_service.notify(
                        "stream_ended",
                        f"LAN stream ended: {user_name} - {display_title}",
                        {
                            "session_id": session_id,
                            "user_name": user_name,
                            "user_id": user_id,
                            "media_title": display_title,
                            "player": player,
                            "stream_bandwidth_mbps": stream.get("stream_bandwidth_mbps"),
                            "is_lan": True,
                        }
                    )
                return

            logger.info(f"Handling stopped stream: {user_name} - {display_title} (session: {session_id})")

            # Calculate restoration delay for this stream
            stream_info = {
                "media_type": media_type,
                "duration_seconds": stream.get("duration_seconds"),
                "progress_seconds": stream.get("progress_seconds"),
            }
            delay = self.decision_engine.calculate_restoration_delay(stream_info)

            # Calculate bandwidth freed by this stream ending (with overhead, or fixed manual value)
            freed_bandwidth = calculate_stream_bandwidth(
                stream,
                self.config.bandwidth.streams.overhead_percent,
                bandwidth_calculation=self.config.bandwidth.streams.bandwidth_calculation,
                manual_per_stream=self.config.bandwidth.streams.manual_per_stream,
            )

            logger.info(
                f"Stream stopped: user={user_id}, player={player}, "
                f"bandwidth={freed_bandwidth:.1f} Mbps, delay={delay}s"
            )

            # Schedule bandwidth reservation with user/player tracking
            await self.schedule_restoration(
                delay,
                freed_bandwidth,
                user_id=user_id,
                player=player,
                user_name=user_name,
                media_title=display_title
            )

            # Clear stored session bandwidth if any
            if session_id:
                await self.clear_session_bandwidth(session_id)

            # Send notification
            if self.notification_service:
                await self.notification_service.notify(
                    "stream_ended",
                    f"Stream ended: {user_name} - {display_title}",
                    {
                        "session_id": session_id,
                        "user_name": user_name,
                        "user_id": user_id,
                        "media_title": display_title,
                        "player": player,
                        "stream_bandwidth_mbps": stream.get("stream_bandwidth_mbps"),
                    }
                )

        except Exception as e:
            logger.error(f"Error handling stopped stream {stream.get('session_id')}: {e}")

    async def _download_poll_loop(self):
        """Download client monitoring loop."""
        while self._running:
            try:
                await self._download_poll_cycle()
            except Exception as e:
                logger.error(f"Error in download polling cycle: {e}")

            await asyncio.sleep(self.config.system.update_frequency)

    async def _download_poll_cycle(self):
        """Monitor download clients and apply throttling."""
        try:
            # Get download client stats
            download_stats = await self.controller_manager.get_client_stats()
            self._cached_client_stats = download_stats  # Cache for status API
            old_stats = download_stats.copy()

            # Track download client unreachable/recovery
            for client_id, stats in download_stats.items():
                client_name = stats.get("client_name", client_id)
                if "error" in stats:
                    # Client has error - increment failure count
                    self._client_unreachable_counts[client_id] = self._client_unreachable_counts.get(client_id, 0) + 1
                    count = self._client_unreachable_counts[client_id]
                    if count >= self._plex_max_failures and not self._client_unreachable_warned.get(client_id):
                        self._client_unreachable_warned[client_id] = True
                        logger.error(f"{client_name} has been unreachable for {count} consecutive polls")
                        if self.notification_service:
                            await self.notification_service.notify(
                                "service_unreachable",
                                f"{client_name} is unreachable.",
                                {"service": client_name, "status": "unreachable", "consecutive_failures": count}
                            )
                else:
                    # Client is healthy - check if recovering from warned state
                    if self._client_unreachable_warned.get(client_id):
                        logger.info(f"{client_name} connection restored")
                        if self.notification_service:
                            await self.notification_service.notify(
                                "service_unreachable",
                                f"{client_name} is back online.",
                                {"service": client_name, "status": "recovered"}
                            )
                    self._client_unreachable_counts[client_id] = 0
                    self._client_unreachable_warned[client_id] = False

            # Get SNMP data if enabled
            snmp_data = None
            if self.config.snmp.enabled and self.snmp_monitor:
                snmp_failed = False
                try:
                    logger.debug(f"Querying SNMP bandwidth for interface {self.config.snmp.interface}")
                    snmp_data = await self.snmp_monitor.get_bandwidth()
                    if snmp_data:
                        logger.info(
                            f"SNMP: {snmp_data['download']:.2f} Mbps down, {snmp_data['upload']:.2f} Mbps up"
                        )
                        self._last_snmp_data = snmp_data  # Store for status API
                    else:
                        logger.debug("SNMP get_bandwidth() returned None (establishing baseline or query failed)")
                        self._last_snmp_data = None  # Clear so status API shows SNMP unreachable
                        snmp_failed = True
                except Exception as e:
                    logger.warning(f"SNMP monitoring failed: {e}")
                    self._last_snmp_data = None  # Clear so status API shows SNMP unreachable
                    snmp_failed = True

                # Track SNMP unreachable/recovery notifications
                if snmp_failed:
                    self._snmp_consecutive_failures += 1
                    if self._snmp_consecutive_failures >= self._plex_max_failures and not self._snmp_unreachable_warned:
                        self._snmp_unreachable_warned = True
                        logger.error(f"SNMP has been unreachable for {self._snmp_consecutive_failures} consecutive polls")
                        if self.notification_service:
                            await self.notification_service.notify(
                                "service_unreachable",
                                "SNMP monitor is unreachable.",
                                {"service": "SNMP", "status": "unreachable", "consecutive_failures": self._snmp_consecutive_failures}
                            )
                else:
                    if self._snmp_unreachable_warned:
                        logger.info("SNMP connection restored")
                        if self.notification_service:
                            await self.notification_service.notify(
                                "service_unreachable",
                                "SNMP monitor is back online.",
                                {"service": "SNMP", "status": "recovered"}
                            )
                    self._snmp_consecutive_failures = 0
                    self._snmp_unreachable_warned = False

            # Get reserved bandwidth (binary reservation until timer expires)
            reserved_bandwidth = await self.get_reserved_bandwidth()

            # Get download reserve from held upload reservations
            reserved_download_bandwidth = await self.get_reserved_download_bandwidth()

            # Get active temporary limits (if any)
            temp_download_limit, temp_upload_limit = await self.get_active_temporary_limits()

            # Calculate throttling decisions using cached stream data + reserved bandwidth
            decisions = self.decision_engine.calculate_throttle(
                self._cached_streams,
                download_stats,
                snmp_data,
                reserved_bandwidth,
                temp_download_limit,
                temp_upload_limit,
                reserved_download_bandwidth
            )

            # Apply decisions if any
            if decisions:
                await self.controller_manager.apply_decisions(decisions)

                # Get new stats after applying decisions
                new_stats = await self.controller_manager.get_client_stats()

                # Save throttle decisions to database (per-client-id; separate
                # entries for download and upload).
                if self._get_db_session:
                    try:
                        dl_per_client = build_decision_per_client(old_stats, new_stats, "download")
                        ul_per_client = build_decision_per_client(old_stats, new_stats, "upload")
                        if dl_per_client or ul_per_client:
                            async with self._get_db_session() as db:
                                if dl_per_client:
                                    names = sorted({e["name"] for e in dl_per_client.values()})
                                    dl_reason = (
                                        f"{names[0]} adjusted" if len(names) == 1
                                        else f"{len(names)} clients adjusted"
                                    )
                                    db.add(ThrottleDecision(
                                        timestamp=datetime.now(timezone.utc),
                                        decision_type="throttle" if self._cached_streams else "restore",
                                        reason=dl_reason,
                                        active_streams=len(self._cached_streams),
                                        stream_session_ids=[s.get("session_id") for s in self._cached_streams],
                                        total_required_bandwidth=sum(
                                            s.get("stream_bandwidth_mbps", 0) for s in self._cached_streams
                                        ),
                                        per_client=dl_per_client,
                                        snmp_download_usage=snmp_data.get("download") if snmp_data else None,
                                        triggered_by="polling",
                                    ))
                                    logger.debug(f"Saved download decision: {dl_reason}")
                                if ul_per_client:
                                    stream_count = len(self._cached_streams)
                                    ul_reason = (
                                        "No active streams" if stream_count == 0
                                        else f"{stream_count} active stream(s)"
                                    )
                                    db.add(ThrottleDecision(
                                        timestamp=datetime.now(timezone.utc),
                                        decision_type="throttle" if self._cached_streams else "restore",
                                        reason=ul_reason,
                                        active_streams=stream_count,
                                        stream_session_ids=[s.get("session_id") for s in self._cached_streams],
                                        total_required_bandwidth=sum(
                                            s.get("stream_bandwidth_mbps", 0) for s in self._cached_streams
                                        ),
                                        per_client=ul_per_client,
                                        snmp_upload_usage=snmp_data.get("upload") if snmp_data else None,
                                        triggered_by="polling",
                                    ))
                                    logger.debug(f"Saved upload decision: {ul_reason}")
                                await db.commit()
                    except Exception as e:
                        logger.error(f"Error saving throttle decision to database: {e}")

                # TODO: Send notifications
                # TODO: Update WebSocket clients

            # Record bandwidth metrics to database
            if self._get_db_session:
                try:
                    async with self._get_db_session() as db:
                        # Calculate total stream bandwidth (use bitrate - media file's encoded rate)
                        total_stream_bandwidth = sum(
                            s.get("stream_bitrate_mbps", 0) for s in self._cached_streams
                        )

                        # Calculate actual Plex bandwidth (network throughput from /statistics/bandwidth)
                        total_stream_actual_bandwidth = sum(
                            s.get("stream_bandwidth_mbps", 0) for s in self._cached_streams
                        )

                        # Split streams by WAN/LAN
                        wan_streams = [s for s in self._cached_streams if not s.get("is_lan", False)]
                        lan_streams = [s for s in self._cached_streams if s.get("is_lan", False)]

                        # Per-client-id breakdown (keeps every client, including
                        # multiple of the same type) for the chart.
                        per_client = build_per_client_metrics(download_stats)

                        # Create bandwidth metric record
                        metric = BandwidthMetric(
                            timestamp=datetime.now(timezone.utc),
                            # Download metrics
                            total_download_limit=self.config.bandwidth.download.total_limit,
                            qbittorrent_download_speed=sum_stat_by_type(download_stats, "qbittorrent", "download_speed"),
                            qbittorrent_download_limit=sum_stat_by_type(download_stats, "qbittorrent", "download_limit"),
                            sabnzbd_download_speed=sum_stat_by_type(download_stats, "sabnzbd", "download_speed"),
                            sabnzbd_download_limit=sum_stat_by_type(download_stats, "sabnzbd", "download_limit"),
                            nzbget_download_speed=sum_stat_by_type(download_stats, "nzbget", "download_speed"),
                            nzbget_download_limit=sum_stat_by_type(download_stats, "nzbget", "download_limit"),
                            transmission_download_speed=sum_stat_by_type(download_stats, "transmission", "download_speed"),
                            transmission_download_limit=sum_stat_by_type(download_stats, "transmission", "download_limit"),
                            deluge_download_speed=sum_stat_by_type(download_stats, "deluge", "download_speed"),
                            deluge_download_limit=sum_stat_by_type(download_stats, "deluge", "download_limit"),
                            # Upload metrics
                            total_upload_limit=self.config.bandwidth.upload.total_limit,
                            qbittorrent_upload_speed=sum_stat_by_type(download_stats, "qbittorrent", "upload_speed"),
                            qbittorrent_upload_limit=sum_stat_by_type(download_stats, "qbittorrent", "upload_limit"),
                            sabnzbd_upload_speed=sum_stat_by_type(download_stats, "sabnzbd", "upload_speed"),
                            sabnzbd_upload_limit=sum_stat_by_type(download_stats, "sabnzbd", "upload_limit"),
                            transmission_upload_speed=sum_stat_by_type(download_stats, "transmission", "upload_speed"),
                            transmission_upload_limit=sum_stat_by_type(download_stats, "transmission", "upload_limit"),
                            deluge_upload_speed=sum_stat_by_type(download_stats, "deluge", "upload_speed"),
                            deluge_upload_limit=sum_stat_by_type(download_stats, "deluge", "upload_limit"),
                            # SNMP metrics (if available)
                            snmp_download_speed=snmp_data.get("download") if snmp_data else None,
                            snmp_upload_speed=snmp_data.get("upload") if snmp_data else None,
                            # Stream metrics
                            active_streams_count=len(self._cached_streams),
                            total_stream_bandwidth=total_stream_bandwidth,
                            total_stream_actual_bandwidth=total_stream_actual_bandwidth,
                            # WAN/LAN stream split
                            wan_streams_count=len(wan_streams),
                            wan_stream_bandwidth=sum(s.get("stream_bitrate_mbps", 0) for s in wan_streams),
                            lan_streams_count=len(lan_streams),
                            lan_stream_bandwidth=sum(s.get("stream_bitrate_mbps", 0) for s in lan_streams),
                            # State
                            is_throttled=bool(decisions),
                            # Per-server breakdown
                            per_server=json.dumps(aggregate_per_server_bandwidth(self._cached_streams)),
                            # Per-client-id breakdown
                            per_client=json.dumps(per_client),
                        )
                        db.add(metric)
                        await db.commit()

                        # Log what was saved including SNMP
                        snmp_info = ""
                        if snmp_data:
                            snmp_info = f", SNMP: {snmp_data.get('download'):.2f}/{snmp_data.get('upload'):.2f} Mbps"
                        logger.debug(f"Saved bandwidth metric: {len(self._cached_streams)} streams, throttled={bool(decisions)}{snmp_info}")
                except Exception as e:
                    logger.error(f"Error saving bandwidth metric to database: {e}")

        except Exception as e:
            logger.error(f"Error in download poll cycle: {e}")
