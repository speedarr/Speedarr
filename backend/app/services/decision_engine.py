"""
Decision engine for calculating bandwidth throttling decisions.
"""
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta, time, timezone
from loguru import logger
from app.config import SpeedarrConfig, TimeBasedScheduleConfig
from app.utils.bandwidth import calculate_stream_bandwidth, filter_streams_for_bandwidth


def is_within_schedule(schedule: TimeBasedScheduleConfig) -> bool:
    """
    Check if current time is within the scheduled time window.

    Handles schedules that cross midnight (e.g., 22:00 to 06:00).
    """
    if not schedule.enabled:
        return False

    try:
        # Parse start and end times
        start_parts = schedule.start_time.split(":")
        end_parts = schedule.end_time.split(":")

        start = time(int(start_parts[0]), int(start_parts[1]))
        end = time(int(end_parts[0]), int(end_parts[1]))

        now = datetime.now(timezone.utc).time()

        if start <= end:
            # Same day schedule (e.g., 09:00 to 17:00)
            return start <= now <= end
        else:
            # Crosses midnight (e.g., 22:00 to 06:00)
            return now >= start or now <= end
    except (ValueError, IndexError) as e:
        logger.warning(f"Invalid schedule time format: {e}")
        return False


class DecisionEngine:
    """
    Calculates optimal bandwidth allocation based on active streams
    and download client activity.
    """

    # Number of polling intervals before a client is marked as inactive
    INACTIVE_BUFFER_INTERVALS = 6

    def __init__(self, config: SpeedarrConfig):
        self.config = config
        self._last_throttle_time: Dict[str, datetime] = {}
        self._pending_restorations: Dict[str, datetime] = {}
        # Track consecutive intervals each client has been below the active threshold
        self._inactive_counter: Dict[str, int] = {}
        # Track consecutive intervals each upload client has been below the active threshold
        self._upload_inactive_counter: Dict[str, int] = {}

    def calculate_throttle(
        self,
        active_streams: List[Dict[str, Any]],
        download_stats: Dict[str, Dict[str, Any]],
        snmp_data: Optional[Dict[str, float]] = None,
        reserved_bandwidth_mbps: float = 0.0,
        temp_download_limit: Optional[float] = None,
        temp_upload_limit: Optional[float] = None,
        reserved_download_bandwidth_mbps: float = 0.0
    ) -> Dict[str, Dict[str, Any]]:
        """
        Calculate throttling decisions for all download clients.

        Args:
            active_streams: List of active stream dicts
            download_stats: Dict of client stats (qbittorrent, sabnzbd)
            snmp_data: Optional SNMP bandwidth data
            reserved_bandwidth_mbps: Bandwidth reserved from ended streams (Mbps)
            temp_download_limit: Optional temporary download limit override (Mbps)
            temp_upload_limit: Optional temporary upload limit override (Mbps)
            reserved_download_bandwidth_mbps: Download bandwidth reserved from held stream reservations (Mbps)

        Returns:
            Dict mapping client names to decision dicts
        """
        decisions = {}

        # Check if we're in a scheduled time window
        download_in_schedule = is_within_schedule(self.config.bandwidth.download.scheduled)
        upload_in_schedule = is_within_schedule(self.config.bandwidth.upload.scheduled)

        # Use temporary limits if provided, then scheduled limits, then default config
        if temp_download_limit is not None:
            download_total_limit = temp_download_limit
        elif download_in_schedule and self.config.bandwidth.download.scheduled.total_limit > 0:
            download_total_limit = self.config.bandwidth.download.scheduled.total_limit
            logger.debug(f"Using scheduled download limit: {download_total_limit} Mbps")
        else:
            download_total_limit = self.config.bandwidth.download.total_limit

        if temp_upload_limit is not None:
            upload_total_limit = temp_upload_limit
        elif upload_in_schedule and self.config.bandwidth.upload.scheduled.total_limit > 0:
            upload_total_limit = self.config.bandwidth.upload.scheduled.total_limit
            logger.debug(f"Using scheduled upload limit: {upload_total_limit} Mbps")
        else:
            upload_total_limit = self.config.bandwidth.upload.total_limit

        # Calculate required bandwidth for streams (0 if no streams)
        if not active_streams:
            total_stream_bandwidth = 0
            raw_stream_bandwidth = 0
            logger.debug("No active streams, using full bandwidth with allocation rules")
        else:
            # Filter streams based on LAN/WAN config
            bandwidth_streams = filter_streams_for_bandwidth(
                active_streams, self.config.plex.include_lan_streams
            )
            lan_count = len(active_streams) - len(bandwidth_streams)
            if lan_count > 0:
                logger.debug(f"Excluding {lan_count} LAN stream(s) from bandwidth calculations")

            # Calculate raw bandwidth (without overhead)
            raw_stream_bandwidth = sum(
                s.get("stream_bitrate_mbps", 0) for s in bandwidth_streams
            )

            # Calculate required bandwidth for streams (with overhead)
            total_stream_bandwidth = sum(
                calculate_stream_bandwidth(stream, self.config.bandwidth.streams.overhead_percent)
                for stream in bandwidth_streams
            )

        logger.debug(
            f"Streams: {len(active_streams)} | Raw: {raw_stream_bandwidth:.2f} Mbps | With overhead: {total_stream_bandwidth:.2f} Mbps"
        )

        # Calculate download reserve for TCP ACKs/control traffic from active streams
        download_reserve_percent = self.config.bandwidth.streams.download_reserve_percent
        active_download_reserve = total_stream_bandwidth * (download_reserve_percent / 100) if download_reserve_percent > 0 else 0.0
        total_download_reserve = active_download_reserve + reserved_download_bandwidth_mbps

        if total_download_reserve > 0:
            logger.debug(
                f"Download reserve: active={active_download_reserve:.2f} Mbps + holding={reserved_download_bandwidth_mbps:.2f} Mbps = {total_download_reserve:.2f} Mbps"
            )

        # Calculate available bandwidth for downloads
        # Subtract download reserve for TCP ACKs/retransmissions from active and held streams
        available_download = max(0, download_total_limit - total_download_reserve)

        # Apply SNMP constraints if available
        if snmp_data:
            available_download = self._apply_snmp_download_constraint(
                available_download, snmp_data
            )

        # Ensure non-negative download
        available_download = max(0, available_download)

        # Calculate available upload (streams use upload bandwidth)
        # Subtract reserved bandwidth (from recently ended streams - keeps upload limits LOW)
        upload_before_reservation = upload_total_limit - total_stream_bandwidth
        available_upload = max(0, upload_before_reservation - reserved_bandwidth_mbps)

        # Check if plex reserved bandwidth exceeds total upload limit
        # In this case, allocate only 1% per upload client as a safety measure
        plex_exceeds_limit = total_stream_bandwidth > upload_total_limit
        if plex_exceeds_limit:
            # Calculate 1% per upload client
            upload_clients = [c for c, stats in download_stats.items() if stats.get("supports_upload", False)]
            if upload_clients:
                emergency_upload = upload_total_limit * 0.01 * len(upload_clients)
                available_upload = emergency_upload
                logger.warning(
                    f"Plex reserved ({total_stream_bandwidth:.1f} Mbps) exceeds upload limit ({upload_total_limit:.1f} Mbps). "
                    f"Upload clients limited to 1% each."
                )

        # Get all available clients (we always apply limits to all clients)
        all_clients = list(download_stats.keys())

        if not all_clients:
            logger.debug("No download clients configured")
            return decisions

        # Calculate standby bandwidth per client (equal split for idle mode)
        standby_per_client = available_download / len(all_clients) if all_clients else 0

        # Active threshold: 10% of standby bandwidth
        # A client is considered "actively downloading" if its speed exceeds this threshold
        active_threshold = standby_per_client * 0.10

        # Identify which clients are actively downloading, with inactive buffer
        # A client is considered active if:
        #   - Current speed > threshold (resets inactive counter), OR
        #   - It was active recently (inactive counter < buffer threshold)
        active_downloading = []
        for name, stats in download_stats.items():
            current_speed = stats.get("download_speed", 0)
            if current_speed > active_threshold:
                # Client is actively downloading - reset inactive counter
                self._inactive_counter[name] = 0
                active_downloading.append(name)
            else:
                # Client is below threshold - increment inactive counter
                self._inactive_counter[name] = self._inactive_counter.get(name, 0) + 1
                # Still considered "active" if within the buffer period
                if self._inactive_counter[name] < self.INACTIVE_BUFFER_INTERVALS:
                    active_downloading.append(name)
                    logger.debug(
                        f"{name}: Speed {current_speed:.2f} Mbps < threshold {active_threshold:.2f} Mbps, "
                        f"inactive buffer {self._inactive_counter[name]}/{self.INACTIVE_BUFFER_INTERVALS}"
                    )

        # Allocate download bandwidth (independent of streams)
        download_allocations = self._allocate_download_bandwidth(
            all_clients,
            available_download,
            active_downloading,
            use_scheduled=download_in_schedule
        )

        # Calculate upload bandwidth (Plex-aware, qBittorrent only)
        upload_allocations = self._calculate_upload_limits(
            download_stats,
            available_upload,  # Pass the correctly calculated upload limit (includes reservation)
            use_scheduled=upload_in_schedule
        )

        # Calculate total reserved bandwidth (stream bandwidth only)
        reserved_bandwidth = total_stream_bandwidth

        # Build reason string with detailed bandwidth breakdown
        if active_streams:
            reason = (f"Active streams: {len(active_streams)}, "
                     f"Raw: {raw_stream_bandwidth:.1f} Mbps, "
                     f"With Overhead: {total_stream_bandwidth:.1f} Mbps, "
                     f"Reserved: {reserved_bandwidth:.1f} Mbps")
            if reserved_bandwidth_mbps > 0:
                reason += f", Holding: {reserved_bandwidth_mbps:.1f} Mbps"
        else:
            reason = "No active streams"
            if reserved_bandwidth_mbps > 0:
                reason += f", Holding: {reserved_bandwidth_mbps:.1f} Mbps"

        # Apply decisions to all clients
        for client_name in all_clients:
            decisions[client_name] = {
                "action": "throttle",
                "download_limit": round(download_allocations[client_name], 2),
                "upload_limit": round(upload_allocations.get(client_name, 0), 2),
                "reason": reason,
            }

        # Record throttle time
        self._last_throttle_time = {name: datetime.now(timezone.utc) for name in all_clients}

        return decisions

    def _allocate_download_bandwidth(
        self,
        all_clients: List[str],
        available_download: float,
        active_downloading: List[str],
        use_scheduled: bool = False
    ) -> Dict[str, float]:
        """
        Dynamic allocation: Adjusts based on which clients are actively downloading.

        Rules:
        - No clients downloading: Use configured standby percentage split
        - One client downloading: Active gets (100 - safety_net)%, inactive clients share safety_net%
        - Multiple clients downloading: Inactive clients each get safety_net%, active clients
          split remaining bandwidth based on configured active percentages

        The safety net ensures inactive clients always get some bandwidth to detect
        when they become active and need more allocation.

        If use_scheduled=True, uses the scheduled client_percents instead.
        """
        if len(all_clients) == 0:
            return {}

        # Get safety net percentage (default 5%)
        safety_net_percent = getattr(
            self.config.bandwidth.download,
            'inactive_safety_net_percent',
            5
        ) / 100

        # Always allocate to all clients
        allocations = {}

        # Get client percentages from config (use scheduled if in schedule window)
        if use_scheduled and self.config.bandwidth.download.scheduled.client_percents:
            client_percents = self.config.bandwidth.download.scheduled.client_percents
            logger.debug(f"Using scheduled client percentages: {client_percents}")
        else:
            client_percents = self.config.bandwidth.download.client_percents or {}

        # Default equal split (guard against empty list)
        equal_percent = 100.0 / len(all_clients) if all_clients else 0

        def get_client_type(client_id: str) -> str:
            """Extract client type from client ID (e.g., 'sabnzbd_123' -> 'sabnzbd')."""
            # Client IDs are in format 'type_uniqueId', extract just the type
            return client_id.split('_')[0] if '_' in client_id else client_id

        def get_normalized_percents(percents_dict: Dict[str, float]) -> Dict[str, float]:
            """Get normalized percentages for enabled clients only."""
            # Only use percentages for clients that are currently enabled
            # Look up by client type (e.g., 'sabnzbd') since that's how the UI saves them
            raw = {c: percents_dict.get(get_client_type(c), equal_percent) for c in all_clients}
            total = sum(raw.values())
            if total == 0:
                return {c: 1.0 / len(all_clients) for c in all_clients}
            return {c: (v / total) for c, v in raw.items()}

        if len(active_downloading) == 0:
            # No clients downloading: Use equal split for standby mode
            # (client_percents only applies when multiple clients are actively downloading)
            for client in all_clients:
                allocations[client] = available_download / len(all_clients)

            alloc_str = ", ".join(f"{c}: {allocations[c]:.1f} Mbps" for c in all_clients)
            logger.debug(f"Standby mode (equal split) - {alloc_str}")

        elif len(active_downloading) == 1:
            # Single client downloading: Give most bandwidth to active, safety net to each inactive
            active_client = active_downloading[0]
            inactive_clients = [c for c in all_clients if c != active_client]

            # Each inactive client gets the full safety_net_percent
            total_safety_net = safety_net_percent * len(inactive_clients)
            active_percent = 1.0 - total_safety_net

            allocations[active_client] = available_download * active_percent
            for client in inactive_clients:
                allocations[client] = available_download * safety_net_percent

            logger.debug(
                f"Dynamic mode: {active_client} downloading ({active_percent*100:.0f}%), "
                f"others safety net ({safety_net_percent*100:.0f}% each)"
            )

        else:
            # Multiple clients downloading: Active clients split based on percentages,
            # inactive clients get safety net
            inactive_clients = [c for c in all_clients if c not in active_downloading]

            # Calculate total safety net for inactive clients
            total_safety_net = safety_net_percent * len(inactive_clients)
            active_pool = 1.0 - total_safety_net  # Remaining bandwidth for active clients

            # Give inactive clients their safety net
            for client in inactive_clients:
                allocations[client] = available_download * safety_net_percent

            # Normalize active percentages for ONLY the active clients
            if active_downloading:
                # Check if ALL active clients have explicitly configured percentages
                # If not, use equal split to avoid mixing configured and default values
                # Look up by client type since that's how the UI saves them
                all_configured = all(get_client_type(c) in client_percents for c in active_downloading)

                if all_configured:
                    raw_active = {c: client_percents[get_client_type(c)] for c in active_downloading}
                    total_raw = sum(raw_active.values())
                    if total_raw == 0:
                        normalized_active = {c: 1.0 / len(active_downloading) for c in active_downloading}
                    else:
                        normalized_active = {c: (v / total_raw) for c, v in raw_active.items()}
                else:
                    # Equal split when not all clients have configured percentages
                    normalized_active = {c: 1.0 / len(active_downloading) for c in active_downloading}

                # Allocate active pool based on normalized percentages
                for client in active_downloading:
                    allocations[client] = available_download * active_pool * normalized_active[client]

            active_str = ", ".join(f"{c}: {allocations[c]:.1f} Mbps" for c in active_downloading)
            inactive_str = ", ".join(f"{c}: {allocations[c]:.1f} Mbps" for c in inactive_clients) if inactive_clients else "none"
            logger.info(f"Multiple active ({len(active_downloading)}/{len(all_clients)}) - Active: {active_str} | Inactive: {inactive_str}")

        return allocations

    def _calculate_upload_limits(
        self,
        download_stats: Dict[str, Dict[str, Any]],
        available_upload: float,
        use_scheduled: bool = False
    ) -> Dict[str, float]:
        """
        Calculate upload limits for download clients (Plex-aware).

        Upload bandwidth is affected by Plex streams (server uploads to clients).
        Torrent clients use upload bandwidth for seeding.
        Usenet clients don't upload, always get 0.

        Dynamic allocation rules (same as download):
        - No clients uploading: Equal split for idle mode
        - One client uploading: Active gets (100 - safety_net*inactive_count)%, inactive get safety_net% each
        - Multiple clients uploading: Inactive get safety_net% each, active split remaining by percentages

        Args:
            download_stats: Dict of client stats (keyed by client_id, includes supports_upload field)
            available_upload: Available upload bandwidth (already calculated with streams, safety margin, and reservation)
            use_scheduled: Whether to use scheduled percentages

        Returns:
            Dict mapping client IDs to upload limits (Mbps)
        """
        upload_limits = {}

        # Get upload-capable clients based on supports_upload field from stats
        upload_clients = [
            client_id for client_id, stats in download_stats.items()
            if stats.get("supports_upload", False)
        ]

        # Non-upload clients get 0
        for client_id, stats in download_stats.items():
            if not stats.get("supports_upload", False):
                upload_limits[client_id] = 0

        if not upload_clients:
            return upload_limits

        # Get configured upload percentages (use scheduled if in schedule window)
        if use_scheduled and self.config.bandwidth.upload.scheduled.client_percents:
            upload_percents = self.config.bandwidth.upload.scheduled.client_percents
            logger.debug(f"Using scheduled upload client percentages: {upload_percents}")
        else:
            upload_percents = getattr(self.config.bandwidth.upload, 'upload_client_percents', {}) or {}

        # Default equal split percentage (guard against empty list)
        default_percent = 100.0 / len(upload_clients) if upload_clients else 0

        def get_client_type(client_id: str) -> str:
            """Extract client type from client ID (e.g., 'qbittorrent_123' -> 'qbittorrent')."""
            return client_id.split('_')[0] if '_' in client_id else client_id

        # Calculate standby bandwidth per upload client (equal split for idle mode)
        standby_per_client = available_upload / len(upload_clients)

        # Active threshold: 10% of standby bandwidth (same as download)
        active_threshold = standby_per_client * 0.10

        # Identify which clients are actively uploading, with inactive buffer
        active_uploading = []
        for client_id in upload_clients:
            stats = download_stats.get(client_id, {})
            current_upload_speed = stats.get("upload_speed", 0)

            if current_upload_speed > active_threshold:
                # Client is actively uploading - reset inactive counter
                self._upload_inactive_counter[client_id] = 0
                active_uploading.append(client_id)
            else:
                # Client is below threshold - increment inactive counter
                self._upload_inactive_counter[client_id] = self._upload_inactive_counter.get(client_id, 0) + 1
                # Still considered "active" if within the buffer period
                if self._upload_inactive_counter[client_id] < self.INACTIVE_BUFFER_INTERVALS:
                    active_uploading.append(client_id)
                    logger.debug(
                        f"{client_id}: Upload speed {current_upload_speed:.2f} Mbps < threshold {active_threshold:.2f} Mbps, "
                        f"inactive buffer {self._upload_inactive_counter[client_id]}/{self.INACTIVE_BUFFER_INTERVALS}"
                    )

        # Get safety net percentage (use same value as download, default 5%)
        safety_net_percent = getattr(
            self.config.bandwidth.download,
            'inactive_safety_net_percent',
            5
        ) / 100

        # Get raw percentage for a client (falls back to equal split)
        def get_raw_upload_percent(client_id: str) -> float:
            client_type = get_client_type(client_id)
            if client_type in upload_percents:
                return upload_percents[client_type]
            return default_percent

        if len(active_uploading) == 0:
            # No clients uploading: Equal split for standby mode
            for client in upload_clients:
                upload_limits[client] = available_upload / len(upload_clients)

            alloc_str = ", ".join(f"{c}: {upload_limits[c]:.1f} Mbps" for c in upload_clients)
            logger.debug(f"Upload standby mode (equal split) - {alloc_str}")

        elif len(active_uploading) == 1:
            # Single client uploading: Give most bandwidth to active, safety net to each inactive
            active_client = active_uploading[0]
            inactive_clients = [c for c in upload_clients if c != active_client]

            # Each inactive client gets the full safety_net_percent
            total_safety_net = safety_net_percent * len(inactive_clients)
            active_percent = 1.0 - total_safety_net

            upload_limits[active_client] = available_upload * active_percent
            for client in inactive_clients:
                upload_limits[client] = available_upload * safety_net_percent

            logger.debug(
                f"Upload dynamic mode: {active_client} uploading ({active_percent*100:.0f}%), "
                f"others safety net ({safety_net_percent*100:.0f}% each)"
            )

        else:
            # Multiple clients uploading: Active clients split based on percentages,
            # inactive clients get safety net
            inactive_clients = [c for c in upload_clients if c not in active_uploading]

            # Calculate total safety net for inactive clients
            total_safety_net = safety_net_percent * len(inactive_clients)
            active_pool = 1.0 - total_safety_net  # Remaining bandwidth for active clients

            # Give inactive clients their safety net
            for client in inactive_clients:
                upload_limits[client] = available_upload * safety_net_percent

            # Normalize active percentages for ONLY the active clients
            all_configured = all(get_client_type(c) in upload_percents for c in active_uploading)

            if all_configured:
                raw_active = {c: upload_percents[get_client_type(c)] for c in active_uploading}
                total_raw = sum(raw_active.values())
                if total_raw == 0:
                    normalized_active = {c: 1.0 / len(active_uploading) for c in active_uploading}
                else:
                    normalized_active = {c: (v / total_raw) for c, v in raw_active.items()}
            else:
                # Equal split when not all clients have configured percentages
                normalized_active = {c: 1.0 / len(active_uploading) for c in active_uploading}

            # Allocate active pool based on normalized percentages
            for client in active_uploading:
                upload_limits[client] = available_upload * active_pool * normalized_active[client]

            active_str = ", ".join(f"{c}: {upload_limits[c]:.1f} Mbps" for c in active_uploading)
            inactive_str = ", ".join(f"{c}: {upload_limits[c]:.1f} Mbps" for c in inactive_clients) if inactive_clients else "none"
            logger.info(f"Upload multiple active ({len(active_uploading)}/{len(upload_clients)}) - Active: {active_str} | Inactive: {inactive_str}")

        return upload_limits

    def _apply_snmp_download_constraint(
        self,
        available_download: float,
        snmp_data: Dict[str, float]
    ) -> float:
        """Apply SNMP constraints to download bandwidth only."""
        current_download = snmp_data.get("download_speed", 0)
        constrained = max(0, available_download - current_download)
        if constrained < available_download:
            logger.debug(f"SNMP: Download {available_download:.1f} → {constrained:.1f} Mbps")
        return constrained

    def _apply_snmp_constraints(
        self,
        available_download: float,
        available_upload: float,
        snmp_data: Dict[str, float],
        stream_bandwidth: float
    ) -> tuple[float, float]:
        """Apply SNMP network-wide constraints to available bandwidth."""
        # Get current network usage from SNMP
        current_download = snmp_data.get("download_speed", 0)
        current_upload = snmp_data.get("upload_speed", 0)

        # Account for other devices (current usage minus stream bandwidth)
        other_devices_download = max(0, current_download - stream_bandwidth)
        other_devices_upload = max(0, current_upload - stream_bandwidth)

        # Reduce available bandwidth by other device usage
        constrained_download = max(0, available_download - other_devices_download)
        constrained_upload = max(0, available_upload - other_devices_upload)

        if constrained_download < available_download:
            logger.debug(
                f"SNMP constraint applied: Download {available_download:.1f} -> {constrained_download:.1f} Mbps"
            )

        return constrained_download, constrained_upload

    def calculate_restoration_delay(self, stream: Dict[str, Any]) -> int:
        """
        Calculate how long to wait before restoring speeds after stream ends.

        Args:
            stream: Stream data dict with media_type

        Returns:
            Delay in seconds (episode_end or movie_end)
        """
        media_type = (stream.get("media_type") or "").lower()
        delays = self.config.restoration.delays

        # Return delay based on media type (regardless of watch progress)
        if media_type == "episode":
            return delays.episode_end
        elif media_type == "movie":
            return delays.movie_end

        # Default to episode delay for unknown media types
        return delays.episode_end

    def _should_restore(self) -> bool:
        """Check if enough time has passed since last throttle to restore."""
        if not self._last_throttle_time:
            return False

        # Check if all clients have passed restoration delay
        now = datetime.now(timezone.utc)
        default_delay = timedelta(seconds=self.config.restoration.delays.default)

        for throttle_time in self._last_throttle_time.values():
            if now - throttle_time < default_delay:
                return False

        return True

    def _clear_throttle_state(self):
        """Clear throttle state after restoration."""
        self._last_throttle_time.clear()
        self._pending_restorations.clear()
