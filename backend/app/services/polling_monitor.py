"""
Polling monitor service for stream detection and client monitoring.
"""
import asyncio
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime, timedelta, timezone
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from app.clients.plex import PlexClient
from app.config import SpeedarrConfig
from app.services.decision_engine import DecisionEngine
from app.services.controller_manager import ControllerManager
from app.models import BandwidthMetric, ThrottleDecision
from app.utils.bandwidth import calculate_stream_bandwidth
from app.utils.formatting import format_display_title

# Import TYPE_CHECKING to avoid circular imports
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from app.services.notification_service import NotificationService


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

        # Initialize Plex client
        self.plex = PlexClient(
            url=self.config.plex.url,
            token=self.config.plex.token
        )

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
        self._plex_consecutive_failures: int = 0
        self._plex_last_success: Optional[datetime] = None
        self._plex_unreachable_warned: bool = False
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
        await self.plex.close()
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
            if not expires_at or datetime.now(timezone.utc) > expires_at:
                # Expired - clear and return None
                if self._temporary_limits:
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

    async def _plex_poll_loop(self):
        """Plex stream monitoring loop."""
        while self._running:
            try:
                await self._plex_poll_cycle()
            except Exception as e:
                logger.error(f"Error in Plex polling cycle: {e}")

            await asyncio.sleep(self.config.system.update_frequency)

    async def _plex_poll_cycle(self):
        """Check Plex streams and cache them."""
        try:
            # Store old streams before fetching new ones (for detecting stopped streams)
            old_streams = self._cached_streams.copy()
            old_session_ids = {s.get("session_id") for s in old_streams if s.get("session_id")}

            # Try to get active streams from Plex
            try:
                new_streams = await self.plex.get_active_streams()
                # Success - reset failure tracking
                self._plex_consecutive_failures = 0
                self._plex_last_success = datetime.now(timezone.utc)
                if self._plex_unreachable_warned:
                    logger.info("Plex connection restored")
                    self._plex_unreachable_warned = False
                    if self.notification_service:
                        await self.notification_service.notify(
                            "service_unreachable",
                            "Plex server is back online.",
                            {"service": "Plex", "status": "recovered"}
                        )
                self._cached_streams = new_streams
            except Exception as plex_error:
                # Plex unreachable - increment failure counter
                self._plex_consecutive_failures += 1

                if self._plex_consecutive_failures == 1:
                    logger.warning(f"Plex unreachable: {plex_error}. Keeping last known streams ({len(old_streams)} streams).")
                elif self._plex_consecutive_failures <= self._plex_max_failures:
                    logger.debug(f"Plex still unreachable (failure {self._plex_consecutive_failures}/{self._plex_max_failures})")
                elif not self._plex_unreachable_warned:
                    logger.error(f"Plex has been unreachable for {self._plex_consecutive_failures} consecutive polls. "
                                f"Bandwidth limits are being maintained at current levels. "
                                f"Last successful poll: {self._plex_last_success}")
                    self._plex_unreachable_warned = True
                    # Send notification if configured
                    if self.notification_service:
                        await self.notification_service.notify(
                            "service_unreachable",
                            "Plex server is unreachable. Bandwidth limits maintained at current levels.",
                            {"service": "Plex", "status": "unreachable", "consecutive_failures": self._plex_consecutive_failures}
                        )

                # FAILSAFE: Keep the last known streams - do NOT clear to empty
                # This prevents restoring all speeds when Plex is temporarily down
                return  # Skip rest of cycle when Plex is unreachable

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
            if self.notification_service:
                # Use stream_bandwidth_mbps (real-time) with fallback to stream_bitrate_mbps (media file bitrate)
                total_bandwidth = sum(
                    s.get("stream_bandwidth_mbps", 0) or s.get("stream_bitrate_mbps", 0)
                    for s in self._cached_streams
                )
                stream_count = len(self._cached_streams)
                await self.notification_service.check_stream_count_threshold(stream_count, total_bandwidth)
                await self.notification_service.check_stream_bitrate_threshold(total_bandwidth, stream_count)

        except Exception as e:
            logger.error(f"Error in Plex poll cycle: {e}")

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

            # Skip holding bandwidth for LAN streams if toggle is disabled
            if not self.config.plex.include_lan_streams and is_lan:
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

            # Calculate bandwidth freed by this stream ending (with overhead)
            freed_bandwidth = calculate_stream_bandwidth(
                stream,
                self.config.bandwidth.streams.overhead_percent
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

            # Get active temporary limits (if any)
            temp_download_limit, temp_upload_limit = await self.get_active_temporary_limits()

            # Calculate throttling decisions using cached stream data + reserved bandwidth
            decisions = self.decision_engine.calculate_throttle(
                self._cached_streams,
                download_stats,
                snmp_data,
                reserved_bandwidth,
                temp_download_limit,
                temp_upload_limit
            )

            # Apply decisions if any
            if decisions:
                await self.controller_manager.apply_decisions(decisions)

                # Get new stats after applying decisions
                new_stats = await self.controller_manager.get_client_stats()

                # Save throttle decisions to database (separate entries for download and upload)
                if self._get_db_session:
                    try:
                        async with self._get_db_session() as db:
                            # Helper to find first client of a given type (stats are keyed by client ID)
                            def find_stats_by_type(stats_dict: dict, client_type: str) -> dict:
                                for cid, stats in stats_dict.items():
                                    if stats.get("client_type") == client_type:
                                        return stats
                                return {}

                            # Get stats for qbittorrent and sabnzbd (first of each type for DB compatibility)
                            old_qb = find_stats_by_type(old_stats, "qbittorrent")
                            new_qb = find_stats_by_type(new_stats, "qbittorrent")
                            old_sab = find_stats_by_type(old_stats, "sabnzbd")
                            new_sab = find_stats_by_type(new_stats, "sabnzbd")

                            # Check for download limit changes
                            qbit_dl_old = old_qb.get("download_limit")
                            qbit_dl_new = new_qb.get("download_limit")
                            sab_dl_old = old_sab.get("download_limit")
                            sab_dl_new = new_sab.get("download_limit")

                            download_changed = (
                                (qbit_dl_old is not None and qbit_dl_new is not None and qbit_dl_old != qbit_dl_new) or
                                (sab_dl_old is not None and sab_dl_new is not None and sab_dl_old != sab_dl_new)
                            )

                            # Check for upload limit changes
                            qbit_ul_old = old_qb.get("upload_limit")
                            qbit_ul_new = new_qb.get("upload_limit")

                            upload_changed = (qbit_ul_old is not None and qbit_ul_new is not None and qbit_ul_old != qbit_ul_new)

                            # Create download decision entry if download limits changed
                            if download_changed:
                                # Build descriptive reason for download changes
                                download_reason_parts = []
                                qbit_changed = qbit_dl_old is not None and qbit_dl_new is not None and qbit_dl_old != qbit_dl_new
                                sab_changed = sab_dl_old is not None and sab_dl_new is not None and sab_dl_old != sab_dl_new

                                if qbit_changed and sab_changed:
                                    download_reason_parts.append("Both clients adjusted")
                                elif qbit_changed:
                                    if sab_dl_new is None or sab_dl_new == 0:
                                        download_reason_parts.append("Only qBittorrent active")
                                    else:
                                        download_reason_parts.append("qBittorrent adjusted")
                                elif sab_changed:
                                    if qbit_dl_new is None or qbit_dl_new == 0:
                                        download_reason_parts.append("Only SABnzbd active")
                                    else:
                                        download_reason_parts.append("SABnzbd adjusted")

                                download_reason = download_reason_parts[0] if download_reason_parts else "Download rebalanced"

                                download_decision = ThrottleDecision(
                                    timestamp=datetime.now(timezone.utc),
                                    decision_type="throttle" if self._cached_streams else "restore",
                                    reason=download_reason,
                                    active_streams=len(self._cached_streams),
                                    stream_session_ids=[s.get("session_id") for s in self._cached_streams],
                                    total_required_bandwidth=sum(s.get("stream_bandwidth_mbps", 0) for s in self._cached_streams),
                                    qbittorrent_old_download_limit=qbit_dl_old,
                                    qbittorrent_new_download_limit=qbit_dl_new,
                                    sabnzbd_old_download_limit=sab_dl_old,
                                    sabnzbd_new_download_limit=sab_dl_new,
                                    snmp_download_usage=snmp_data.get("download_speed") if snmp_data else None,
                                    triggered_by="polling"
                                )
                                db.add(download_decision)
                                logger.debug(f"Saved download decision: {download_reason}")

                            # Create upload decision entry if upload limits changed
                            if upload_changed:
                                # Build descriptive reason for upload changes
                                stream_count = len(self._cached_streams)
                                if stream_count == 0:
                                    upload_reason = "No active Plex streams"
                                elif stream_count == 1:
                                    upload_reason = "1 active Plex stream"
                                else:
                                    upload_reason = f"{stream_count} active Plex streams"

                                upload_decision = ThrottleDecision(
                                    timestamp=datetime.now(timezone.utc),
                                    decision_type="throttle" if self._cached_streams else "restore",
                                    reason=upload_reason,
                                    active_streams=stream_count,
                                    stream_session_ids=[s.get("session_id") for s in self._cached_streams],
                                    total_required_bandwidth=sum(s.get("stream_bandwidth_mbps", 0) for s in self._cached_streams),
                                    qbittorrent_old_upload_limit=qbit_ul_old,
                                    qbittorrent_new_upload_limit=qbit_ul_new,
                                    snmp_upload_usage=snmp_data.get("upload_speed") if snmp_data else None,
                                    triggered_by="polling"
                                )
                                db.add(upload_decision)
                                logger.debug(f"Saved upload decision: {upload_reason}")

                            if download_changed or upload_changed:
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

                        # Helper to find first client of a given type (stats are keyed by client ID)
                        def get_stats_by_type(client_type: str) -> dict:
                            for cid, stats in download_stats.items():
                                if stats.get("client_type") == client_type:
                                    return stats
                            return {}

                        qb_stats = get_stats_by_type("qbittorrent")
                        sab_stats = get_stats_by_type("sabnzbd")
                        nzbget_stats = get_stats_by_type("nzbget")
                        transmission_stats = get_stats_by_type("transmission")
                        deluge_stats = get_stats_by_type("deluge")

                        # Create bandwidth metric record
                        metric = BandwidthMetric(
                            timestamp=datetime.now(timezone.utc),
                            # Download metrics
                            total_download_limit=self.config.bandwidth.download.total_limit,
                            qbittorrent_download_speed=qb_stats.get("download_speed"),
                            qbittorrent_download_limit=qb_stats.get("download_limit"),
                            sabnzbd_download_speed=sab_stats.get("download_speed"),
                            sabnzbd_download_limit=sab_stats.get("download_limit"),
                            nzbget_download_speed=nzbget_stats.get("download_speed"),
                            nzbget_download_limit=nzbget_stats.get("download_limit"),
                            transmission_download_speed=transmission_stats.get("download_speed"),
                            transmission_download_limit=transmission_stats.get("download_limit"),
                            deluge_download_speed=deluge_stats.get("download_speed"),
                            deluge_download_limit=deluge_stats.get("download_limit"),
                            # Upload metrics
                            total_upload_limit=self.config.bandwidth.upload.total_limit,
                            qbittorrent_upload_speed=qb_stats.get("upload_speed"),
                            qbittorrent_upload_limit=qb_stats.get("upload_limit"),
                            sabnzbd_upload_speed=sab_stats.get("upload_speed"),
                            sabnzbd_upload_limit=sab_stats.get("upload_limit"),
                            transmission_upload_speed=transmission_stats.get("upload_speed"),
                            transmission_upload_limit=transmission_stats.get("upload_limit"),
                            deluge_upload_speed=deluge_stats.get("upload_speed"),
                            deluge_upload_limit=deluge_stats.get("upload_limit"),
                            # SNMP metrics (if available)
                            snmp_download_speed=snmp_data.get("download") if snmp_data else None,
                            snmp_upload_speed=snmp_data.get("upload") if snmp_data else None,
                            # Stream metrics
                            active_streams_count=len(self._cached_streams),
                            total_stream_bandwidth=total_stream_bandwidth,
                            total_stream_actual_bandwidth=total_stream_actual_bandwidth,
                            # State
                            is_throttled=bool(decisions)
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
