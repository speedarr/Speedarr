"""
Decision engine for calculating bandwidth throttling decisions.
"""
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta, time, timezone
from loguru import logger
from app.config import SpeedarrConfig, TimeBasedScheduleConfig
from app.constants import HARD_MIN_MBPS
from app.utils.bandwidth import calculate_stream_bandwidth, filter_streams_for_bandwidth
from app.services.demand_allocation import split_weights


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
    # A client capped at the safety net is promoted once it reaches this fraction of its
    # cap, so promotion never depends on the client's limiter overshooting (issue #85).
    PROMOTION_CAP_FRACTION = 0.8

    def __init__(self, config: SpeedarrConfig):
        self.config = config
        self._last_throttle_time: Dict[str, datetime] = {}
        self._pending_restorations: Dict[str, datetime] = {}
        # Track consecutive intervals each client has been below the active threshold
        self._inactive_counter: Dict[str, int] = {}
        # Track consecutive intervals each upload client has been below the active threshold
        self._upload_inactive_counter: Dict[str, int] = {}

    def _floor(self, limit: float, configured_min: float) -> float:
        """Clamp a throttle allocation so it is never 0 (which clients read as 'unlimited')."""
        return max(limit, configured_min, HARD_MIN_MBPS)

    def _safety_net_fraction(self) -> float:
        """Inactive safety net as a fraction (default 5%). Upload reuses the download value."""
        return getattr(self.config.bandwidth.download, 'inactive_safety_net_percent', 5) / 100

    def _download_percents(self, use_scheduled: bool) -> Dict[str, int]:
        if use_scheduled and self.config.bandwidth.download.scheduled.client_percents:
            logger.debug(f"Using scheduled client percentages: {self.config.bandwidth.download.scheduled.client_percents}")
            return self.config.bandwidth.download.scheduled.client_percents
        return self.config.bandwidth.download.client_percents or {}

    def _upload_percents(self, use_scheduled: bool) -> Dict[str, int]:
        if use_scheduled and self.config.bandwidth.upload.scheduled.client_percents:
            logger.debug(f"Using scheduled upload client percentages: {self.config.bandwidth.upload.scheduled.client_percents}")
            return self.config.bandwidth.upload.scheduled.client_percents
        return getattr(self.config.bandwidth.upload, 'upload_client_percents', {}) or {}

    def _target_split(
        self,
        clients: List[str],
        available: float,
        active: List[str],
        percents: Dict[str, int],
        safety_net_fraction: float,
        direction: str,
    ) -> Dict[str, float]:
        """
        Today's allocation rules as one pure function, shared by download and upload.

        - No active clients: equal split (standby).
        - Otherwise every inactive client gets the safety net, and the active clients
          split the rest by their configured percents (all configured or equal).
          With one active client that is simply "everything but the safety nets".
        """
        if not clients:
            return {}
        if not active:
            alloc = {c: available / len(clients) for c in clients}
            logger.debug(f"{direction} standby mode (equal split) - "
                         + ", ".join(f"{c}: {v:.1f} Mbps" for c, v in alloc.items()))
            return alloc

        inactive = [c for c in clients if c not in active]
        active_pool = 1.0 - safety_net_fraction * len(inactive)
        alloc = {c: available * safety_net_fraction for c in inactive}
        weights = split_weights(active, percents)
        for c in active:
            alloc[c] = available * active_pool * weights[c]

        if len(active) == 1:
            logger.debug(
                f"{direction} dynamic mode: {active[0]} active ({active_pool * 100:.0f}%), "
                f"others safety net ({safety_net_fraction * 100:.0f}% each)"
            )
        else:
            active_str = ", ".join(f"{c}: {alloc[c]:.1f} Mbps" for c in active)
            inactive_str = ", ".join(f"{c}: {alloc[c]:.1f} Mbps" for c in inactive) if inactive else "none"
            logger.info(
                f"{direction.capitalize()} multiple active ({len(active)}/{len(clients)}) - "
                f"Active: {active_str} | Inactive: {inactive_str}"
            )
        return alloc

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
            bandwidth_streams = filter_streams_for_bandwidth(active_streams)
            lan_count = len(active_streams) - len(bandwidth_streams)
            if lan_count > 0:
                logger.debug(f"Excluding {lan_count} LAN stream(s) from bandwidth calculations")

            # Calculate raw bandwidth (without overhead)
            raw_stream_bandwidth = sum(
                s.get("stream_bitrate_mbps", 0) for s in bandwidth_streams
            )

            # Calculate required bandwidth for streams (with overhead, or fixed manual value)
            streams_config = self.config.bandwidth.streams
            total_stream_bandwidth = sum(
                calculate_stream_bandwidth(
                    stream,
                    streams_config.overhead_percent,
                    bandwidth_calculation=streams_config.bandwidth_calculation,
                    manual_per_stream=streams_config.manual_per_stream,
                )
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
                available_download, snmp_data, download_stats
            )

        # Ensure non-negative download
        available_download = max(0, available_download)

        # Calculate available upload (streams use upload bandwidth)
        # Subtract reserved bandwidth (from recently ended streams - keeps upload limits LOW)
        upload_before_reservation = upload_total_limit - total_stream_bandwidth
        available_upload = max(0, upload_before_reservation - reserved_bandwidth_mbps)

        # Get all available clients (we always apply limits to all clients)
        all_clients = list(download_stats.keys())

        if not all_clients:
            logger.debug("No download clients configured")
            return decisions

        # Calculate standby bandwidth per client (equal split for idle mode)
        standby_per_client = available_download / len(all_clients) if all_clients else 0

        # Active threshold: 10% of standby bandwidth, but never above 80% of the safety-net
        # cap an inactive client is held to (with two clients the two are otherwise equal).
        safety_net_fraction = self._safety_net_fraction()
        active_threshold = min(
            standby_per_client * 0.10,
            available_download * safety_net_fraction * self.PROMOTION_CAP_FRACTION,
        )

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
        dl_percents = self._download_percents(download_in_schedule)
        download_allocations = self._target_split(
            all_clients, available_download, active_downloading,
            dl_percents, safety_net_fraction, "download",
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

        # Apply decisions to all clients, flooring throttles so a limit of 0
        # (which clients treat as "unlimited") can never be emitted. See issue #43.
        dl_min = self.config.bandwidth.download.min_limit_mbps
        ul_min = self.config.bandwidth.upload.min_limit_mbps
        for client_name in all_clients:
            download_limit = self._floor(download_allocations[client_name], dl_min)
            # Upload floor only applies to upload-capable clients; others keep 0.
            if download_stats.get(client_name, {}).get("supports_upload", False):
                upload_limit = self._floor(upload_allocations.get(client_name, 0), ul_min)
            else:
                upload_limit = 0
            decisions[client_name] = {
                "action": "throttle",
                "download_limit": round(download_limit, 2),
                "upload_limit": round(upload_limit, 2),
                "reason": reason,
            }

        # Record throttle time
        self._last_throttle_time = {name: datetime.now(timezone.utc) for name in all_clients}

        return decisions

    def _calculate_upload_limits(
        self,
        download_stats: Dict[str, Dict[str, Any]],
        available_upload: float,
        use_scheduled: bool = False
    ) -> Dict[str, float]:
        """
        Upload limits for upload-capable clients (torrents). Usenet clients get 0.

        Active detection mirrors the download side (10% of standby, six-poll buffer);
        the split itself is the shared _target_split.
        """
        upload_limits: Dict[str, float] = {
            cid: 0 for cid, s in download_stats.items() if not s.get("supports_upload", False)
        }
        upload_clients = [cid for cid, s in download_stats.items() if s.get("supports_upload", False)]
        if not upload_clients:
            return upload_limits

        percents = self._upload_percents(use_scheduled)
        safety_net_fraction = self._safety_net_fraction()

        standby_per_client = available_upload / len(upload_clients)
        active_threshold = min(
            standby_per_client * 0.10,
            available_upload * safety_net_fraction * self.PROMOTION_CAP_FRACTION,
        )

        active_uploading = []
        for client_id in upload_clients:
            current_upload_speed = download_stats.get(client_id, {}).get("upload_speed", 0)
            if current_upload_speed > active_threshold:
                self._upload_inactive_counter[client_id] = 0
                active_uploading.append(client_id)
            else:
                self._upload_inactive_counter[client_id] = self._upload_inactive_counter.get(client_id, 0) + 1
                if self._upload_inactive_counter[client_id] < self.INACTIVE_BUFFER_INTERVALS:
                    active_uploading.append(client_id)
                    logger.debug(
                        f"{client_id}: Upload speed {current_upload_speed:.2f} Mbps < threshold {active_threshold:.2f} Mbps, "
                        f"inactive buffer {self._upload_inactive_counter[client_id]}/{self.INACTIVE_BUFFER_INTERVALS}"
                    )

        upload_limits.update(self._target_split(
            upload_clients, available_upload, active_uploading,
            percents, safety_net_fraction, "upload",
        ))
        return upload_limits

    def _apply_snmp_download_constraint(
        self,
        available_download: float,
        snmp_data: Dict[str, float],
        download_stats: Dict[str, Dict[str, Any]]
    ) -> float:
        """Apply SNMP constraints to download bandwidth only.

        Subtracts only non-managed (other device) traffic from available bandwidth.
        SNMP reports total WAN download which includes managed client traffic,
        so we subtract managed client speeds to avoid double-counting.
        """
        current_download = snmp_data.get("download", 0)
        managed_download = sum(
            stats.get("download_speed", 0) for stats in download_stats.values()
        )
        other_usage = max(0, current_download - managed_download)
        constrained = max(0, available_download - other_usage)
        if constrained < available_download:
            logger.debug(
                f"SNMP: Download {available_download:.1f} → {constrained:.1f} Mbps "
                f"(SNMP total: {current_download:.1f}, managed clients: {managed_download:.1f}, "
                f"other devices: {other_usage:.1f})"
            )
        return constrained

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
