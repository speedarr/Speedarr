"""
Controller manager for applying throttling decisions to download clients.
"""
import asyncio
from typing import Any, Callable, Dict, Optional
from loguru import logger
from app.clients import QBittorrentClient, SABnzbdClient, create_download_client
from app.config import SpeedarrConfig, FailsafeConfig
from app.constants import HARD_MIN_MBPS


class ControllerManager:
    """
    Manages download clients and applies throttling decisions.
    """

    def __init__(self, config: SpeedarrConfig):
        self.config = config
        self.clients: Dict[str, Any] = {}  # client_id -> client instance
        self.client_configs: Dict[str, Any] = {}  # client_id -> client config (for type, name lookup)
        # Serializes bulk limit writes (apply vs restore/remove) - issue #78 race
        self._write_lock = asyncio.Lock()
        self._initialize_clients()

    def _initialize_clients(self):
        """Initialize download client connections."""
        # Use the unified download_clients list
        enabled_clients = self.config.get_enabled_download_clients()

        for client_config in enabled_clients:
            try:
                client = create_download_client(client_config)
                # Use client ID as key to support multiple clients of the same type
                self.clients[client_config.id] = client
                self.client_configs[client_config.id] = client_config
                logger.info(f"{client_config.name} ({client_config.id}) client initialized")
            except Exception as e:
                logger.error(f"Failed to initialize {client_config.name}: {e}")

    async def close_all(self):
        """Close all client connections in parallel."""
        async def close_client(name: str, client: Any) -> None:
            try:
                if hasattr(client, 'close'):
                    await client.close()
            except Exception as e:
                logger.error(f"Error closing {name} client: {e}")

        if self.clients:
            await asyncio.gather(*[
                close_client(name, client)
                for name, client in self.clients.items()
            ])
        self.clients.clear()
        self.client_configs.clear()

    async def reload_clients(self, config: SpeedarrConfig) -> Dict[str, bool]:
        """
        Reload download clients with new configuration.

        Args:
            config: New SpeedarrConfig

        Returns:
            Dict mapping client names to connection test results
        """
        logger.info("Reloading download clients with new configuration")

        # Close existing clients
        await self.close_all()

        # Update config
        self.config = config

        # Reinitialize with new config
        self._initialize_clients()

        # Test connections
        results = await self.test_connections()

        logger.info(f"Client reload complete: {results}")
        return results

    async def test_connections(self) -> Dict[str, bool]:
        """Test connections to all clients in parallel."""
        async def test_client(name: str, client: Any) -> tuple[str, bool]:
            try:
                result = await client.test_connection()
                return (name, result)
            except Exception as e:
                logger.error(f"Failed to test {name}: {e}")
                return (name, False)

        if not self.clients:
            return {}

        results_list = await asyncio.gather(*[
            test_client(name, client)
            for name, client in self.clients.items()
        ])
        return dict(results_list)

    async def get_client_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get stats from all clients in parallel. Stats include client_type for decision engine."""
        async def get_stats_for_client(client_id: str, client: Any) -> tuple[str, Dict[str, Any]]:
            client_config = self.client_configs.get(client_id)
            try:
                client_stats = await client.get_stats()
                # Add client metadata for decision engine
                if client_config:
                    client_stats["client_type"] = client_config.type
                    client_stats["client_name"] = client_config.name
                    client_stats["supports_upload"] = client_config.supports_upload
                return (client_id, client_stats)
            except Exception as e:
                logger.error(f"Failed to get stats from {client_id}: {e}")
                return (client_id, {
                    "active": False,
                    "error": str(e),
                    "client_type": client_config.type if client_config else None,
                    "client_name": client_config.name if client_config else client_id,
                    "supports_upload": client_config.supports_upload if client_config else False,
                })

        if not self.clients:
            return {}

        results_list = await asyncio.gather(*[
            get_stats_for_client(client_id, client)
            for client_id, client in self.clients.items()
        ])
        return dict(results_list)

    async def apply_decisions(
        self,
        decisions: Dict[str, Dict[str, Any]],
        abort_if: Optional[Callable[[], bool]] = None,
    ) -> Dict[str, bool]:
        """
        Apply throttling decisions to download clients.

        Args:
            decisions: Dict mapping client names to decision dicts
            abort_if: Optional gate re-checked under the write lock, right
                before any client writes happen. If it returns True, no
                writes are made and {} is returned - issue #78 race, so a
                poll tick that passed the outer gate before I/O can't land
                writes after a concurrent disable/restore.

        Returns:
            Dict mapping client names to success status
        """
        async with self._write_lock:
            if abort_if is not None and abort_if():
                logger.info("Skipping decision apply - throttling state changed mid-tick")
                return {}

            results = {}

            # Collect download and upload info separately
            download_info = []
            upload_info = []

            for client_name, decision in decisions.items():
                if client_name not in self.clients:
                    logger.warning(f"Unknown client in decisions: {client_name}")
                    continue

                client = self.clients[client_name]
                action = decision.get("action")

                try:
                    if action == "throttle":
                        await client.set_speed_limits(
                            download_limit=decision.get("download_limit"),
                            upload_limit=decision.get("upload_limit")
                        )

                        # Collect download info
                        download_info.append(
                            f"{client_name}: {decision.get('download_limit')} Mbps"
                        )

                        # Collect upload info (only if > 0)
                        upload_limit = decision.get('upload_limit', 0)
                        if upload_limit > 0:
                            upload_info.append(
                                f"{client_name}: {upload_limit} Mbps"
                            )

                        results[client_name] = True

                    elif action == "restore":
                        await client.restore_speed_limits()
                        logger.info(f"Restored {client_name} to normal speeds")
                        results[client_name] = True

                    else:
                        logger.warning(f"Unknown action for {client_name}: {action}")
                        results[client_name] = False

                except Exception as e:
                    logger.error(f"Failed to apply decision to {client_name}: {e}")
                    results[client_name] = False

            # Log download limits (no stream info)
            if download_info:
                logger.info(f"Download limits | {' | '.join(download_info)}")

            # Log upload limits (with stream info)
            if upload_info:
                # Extract stream info from reason
                reason = next(iter(decisions.values())).get("reason", "")
                logger.info(f"Upload limits | {' | '.join(upload_info)} | {reason}")

            return results

    async def restore_all_speeds(self, retries: int = 3, retry_delay: float = 1.0) -> Dict[str, bool]:
        """
        Restore all clients to normal speeds in parallel with retry logic.

        Args:
            retries: Number of retry attempts per client (default: 3)
            retry_delay: Delay between retries in seconds (default: 1.0)

        Returns:
            Dict mapping client names to success status
        """
        async def restore_client_with_retry(name: str, client: Any) -> tuple[str, bool]:
            for attempt in range(1, retries + 1):
                try:
                    await client.restore_speed_limits()
                    logger.info(f"Restored {name} to normal speeds")
                    return (name, True)
                except Exception as e:
                    if attempt < retries:
                        logger.warning(f"Failed to restore {name} (attempt {attempt}/{retries}): {e}")
                        await asyncio.sleep(retry_delay)
                    else:
                        logger.error(f"Failed to restore {name} after {retries} attempts: {e}")
                        return (name, False)
            return (name, False)

        if not self.clients:
            return {}

        async with self._write_lock:
            results_list = await asyncio.gather(*[
                restore_client_with_retry(name, client)
                for name, client in self.clients.items()
            ])
        return dict(results_list)

    async def remove_all_limits(self, retries: int = 3, retry_delay: float = 1.0) -> Dict[str, bool]:
        """
        Set every client to unlimited (issue #78 disable semantics).

        Unlike restore_all_speeds, this does not depend on captured
        _original_limits - "disabled" means Speedarr leaves no limits behind.
        Each adapter's set_unlimited() maps to its native unlimited
        (qBittorrent 0, Transmission enabled=false, Deluge -1, SABnzbd 0
        written directly bypassing the issue-#43 floor, NZBGet 0).
        """
        async def remove_client_with_retry(name: str, client: Any) -> tuple[str, bool]:
            for attempt in range(1, retries + 1):
                try:
                    await client.set_unlimited()
                    logger.info(f"Removed all speed limits from {name}")
                    return (name, True)
                except Exception as e:
                    if attempt < retries:
                        logger.warning(f"Failed to remove limits on {name} (attempt {attempt}/{retries}): {e}")
                        await asyncio.sleep(retry_delay)
                    else:
                        logger.error(f"Failed to remove limits on {name} after {retries} attempts: {e}")
                        return (name, False)
            return (name, False)

        if not self.clients:
            return {}

        async with self._write_lock:
            results_list = await asyncio.gather(*[
                remove_client_with_retry(name, client)
                for name, client in self.clients.items()
            ])
        return dict(results_list)

    def _split_shutdown_speed(
        self,
        total_mbps: float,
        target_ids: list,
        percents: Dict[str, float],
    ) -> Dict[str, float]:
        """
        Split a total shutdown speed across clients by configured per-client percentages.

        Falls back to equal split unless every target client id has a configured
        percentage (same rule as the decision engine's client_percents handling).

        Every per-client limit is floored to HARD_MIN_MBPS so a shutdown speed of
        0 (or a 0% client share) becomes a non-zero trickle rather than 0, which
        clients read as "unlimited". Mirrors the live-throttle floor (#43). See #48.
        """
        if not target_ids:
            return {}

        all_configured = all(client_id in percents for client_id in target_ids)
        if all_configured:
            raw = {c: percents[c] for c in target_ids}
            total_raw = sum(raw.values())
            if total_raw > 0:
                return {c: max(total_mbps * (v / total_raw), HARD_MIN_MBPS) for c, v in raw.items()}

        return {c: max(total_mbps / len(target_ids), HARD_MIN_MBPS) for c in target_ids}

    async def apply_shutdown_speeds(
        self,
        failsafe: FailsafeConfig,
        retries: int = 3,
        retry_delay: float = 1.0,
    ) -> Dict[str, bool]:
        """
        Apply configured failsafe shutdown speeds to clients in parallel.

        Directions with a configured total are split across clients per the
        failsafe percent config; unset directions are restored to normal speeds.
        Upload limits only apply to clients that support upload (torrents).

        Args:
            failsafe: Failsafe config (passed explicitly; self.config may be stale)
            retries: Number of retry attempts per client (default: 3)
            retry_delay: Delay between retries in seconds (default: 1.0)

        Returns:
            Dict mapping client IDs to success status
        """
        if not self.clients:
            return {}

        download_limits: Dict[str, float] = {}
        if failsafe.shutdown_download_speed is not None:
            download_limits = self._split_shutdown_speed(
                failsafe.shutdown_download_speed,
                list(self.clients.keys()),
                failsafe.shutdown_download_client_percents,
            )

        upload_limits: Dict[str, float] = {}
        if failsafe.shutdown_upload_speed is not None:
            upload_targets = [
                client_id for client_id in self.clients
                if self.client_configs[client_id].supports_upload
            ]
            upload_limits = self._split_shutdown_speed(
                failsafe.shutdown_upload_speed,
                upload_targets,
                failsafe.shutdown_upload_client_percents,
            )

        async def apply_to_client(client_id: str, client: Any) -> tuple[str, bool]:
            dl = download_limits.get(client_id)
            ul = upload_limits.get(client_id)
            for attempt in range(1, retries + 1):
                try:
                    # Restore first so unset directions return to normal speeds,
                    # then overlay the shutdown limits (None = leave unchanged)
                    await client.restore_speed_limits()
                    if dl is not None or ul is not None:
                        await client.set_speed_limits(download_limit=dl, upload_limit=ul)
                    logger.info(
                        f"Shutdown speeds applied to {client_id}: "
                        f"DL={f'{dl:.1f} Mbps' if dl is not None else 'restored'}, "
                        f"UL={f'{ul:.1f} Mbps' if ul is not None else 'restored'}"
                    )
                    return (client_id, True)
                except Exception as e:
                    if attempt < retries:
                        logger.warning(f"Failed to apply shutdown speeds to {client_id} (attempt {attempt}/{retries}): {e}")
                        await asyncio.sleep(retry_delay)
                    else:
                        logger.error(f"Failed to apply shutdown speeds to {client_id} after {retries} attempts: {e}")
                        return (client_id, False)
            return (client_id, False)

        results_list = await asyncio.gather(*[
            apply_to_client(client_id, client)
            for client_id, client in self.clients.items()
        ])
        return dict(results_list)

