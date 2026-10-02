"""
Controller manager for applying throttling decisions to download clients.
"""
import asyncio
from typing import Any, Callable, Dict, Optional, Tuple
from loguru import logger
from app.clients import QBittorrentClient, SABnzbdClient, create_download_client
from app.clients.base import RestoreOutcome
from app.config import SpeedarrConfig, FailsafeConfig
from app.constants import HARD_MIN_MBPS
from app.services import client_baselines


def _figure(mbps: float) -> str:
    return "unlimited" if not mbps else f"{mbps:.1f} Mbps"


def describe_limits(limits: Dict[str, float], with_upload: bool) -> str:
    """'DL unlimited, UL 20.0 Mbps' for the restore log lines; no UL part for download-only clients."""
    text = f"DL {_figure(limits.get('download_limit', 0))}"
    if with_upload:
        text += f", UL {_figure(limits.get('upload_limit', 0))}"
    return text


def restore_counts(outcomes: Dict[str, RestoreOutcome]) -> str:
    """'3 restored, 1 nothing to restore, 1 failed'."""
    values = list(outcomes.values())
    return (
        f"{values.count(RestoreOutcome.RESTORED)} restored, "
        f"{values.count(RestoreOutcome.NOTHING_TO_RESTORE)} nothing to restore, "
        f"{values.count(RestoreOutcome.FAILED)} failed"
    )


def restore_message(outcomes: Dict[str, RestoreOutcome]) -> str:
    """The restore-speeds message: what happened, naming every client that was not restored (audit D3-3)."""
    if not outcomes:
        return "No download clients configured"
    total = len(outcomes)
    restored = sum(1 for o in outcomes.values() if o is RestoreOutcome.RESTORED)
    noun = "client" if total == 1 else "clients"
    if restored == total:
        return "Restored 1 client" if total == 1 else f"Restored all {total} clients"
    parts = [f"Restored {restored} of {total} {noun}"]
    nothing = sorted(c for c, o in outcomes.items() if o is RestoreOutcome.NOTHING_TO_RESTORE)
    failed = sorted(c for c, o in outcomes.items() if o is RestoreOutcome.FAILED)
    if nothing:
        parts.append(f"nothing to restore: {', '.join(nothing)}")
    if failed:
        parts.append(f"failed: {', '.join(failed)}")
    return "; ".join(parts)


class ControllerManager:
    """
    Manages download clients and applies throttling decisions.
    """

    def __init__(self, config: SpeedarrConfig, get_db_session: Optional[Callable[[], Any]] = None):
        self.config = config
        self.clients: Dict[str, Any] = {}  # client_id -> client instance
        self.client_configs: Dict[str, Any] = {}  # client_id -> client config (for type, name lookup)
        # Serializes bulk limit writes (apply vs restore/remove) - issue #78 race
        self._write_lock = asyncio.Lock()
        # Torrent clients' normal limits, persisted per client id (audit T4-5)
        self._get_db_session = get_db_session
        self._baselines: Dict[str, Dict[str, Any]] = {}
        self._baselines_loaded = False
        self._baselines_lock = asyncio.Lock()
        # Client ids Speedarr has written to in this process -> the url written to; never captured after
        self._written: Dict[str, str] = {}
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

    async def load_baselines(self) -> None:
        """Load the stored normal limits and drop records for clients that are gone or moved."""
        async with self._baselines_lock:
            await self._load_baselines_locked()

    async def _load_baselines_locked(self) -> None:
        if self._get_db_session is None:
            return
        try:
            async with self._get_db_session() as db:
                records = await client_baselines.load_baselines(db)
                kept = client_baselines.prune_baselines(records, self.config.get_all_download_clients())
                if kept != records:
                    await client_baselines.save_baselines(db, kept)
                    await db.commit()
        except Exception as e:
            logger.warning(f"Could not load download client baselines: {e}")
            return
        self._baselines = kept
        self._baselines_loaded = True

    def _mark_written(self, client_id: str, client: Any) -> None:
        url = getattr(client, "url", "")
        self._written[client_id] = url.rstrip("/") if isinstance(url, str) else ""

    async def _capture_baseline(self, client_id: str, client: Any, client_stats: Dict[str, Any]) -> None:
        """Record a torrent client's limits the first time Speedarr reads them, before it writes (audit T4-5)."""
        if (
            self._get_db_session is None
            or getattr(client, "restores_saved_cap", True)
            or "error" in client_stats
            or "download_limit" not in client_stats
            or "upload_limit" not in client_stats
            or client_id in self._baselines
            or client_id in self._written
        ):
            return
        async with self._baselines_lock:
            if not self._baselines_loaded:
                await self._load_baselines_locked()
                if not self._baselines_loaded:
                    return
            if client_id in self._baselines or client_id in self._written:
                return
            if self.clients.get(client_id) is not client:
                return  # a reload replaced the adapter that was read; its limits are stale
            record = client_baselines.make_record(
                getattr(client, "url", ""), client_stats["download_limit"], client_stats["upload_limit"]
            )
            records = {**self._baselines, client_id: record}
            try:
                async with self._get_db_session() as db:
                    await client_baselines.save_baselines(db, records)
                    await db.commit()
            except Exception as e:
                logger.warning(f"Could not save the normal limits of {client_id}; retrying next poll: {e}")
                return
            self._baselines = records
            logger.info(
                f"Recorded the normal limits of {client_id} "
                f"({describe_limits(record, self._with_upload(client_id))})"
            )

    async def _prune_baselines(self) -> None:
        async with self._baselines_lock:
            if not self._baselines_loaded:
                return
            kept = client_baselines.prune_baselines(self._baselines, self.config.get_all_download_clients())
            if kept == self._baselines:
                return
            self._baselines = kept
            try:
                async with self._get_db_session() as db:
                    await client_baselines.save_baselines(db, kept)
                    await db.commit()
            except Exception as e:
                logger.warning(f"Could not save pruned download client baselines: {e}")

    async def reload_clients(self, config: SpeedarrConfig) -> Dict[str, bool]:
        """
        Reload download clients with new configuration.

        The normal limits survive the rebuild; a client that is gone or now at a different
        address loses its record and its written mark, so it is read afresh (audit T4-5).

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

        urls = {c.id: (c.url or "").rstrip("/") for c in config.get_all_download_clients()}
        self._written = {cid: url for cid, url in self._written.items() if urls.get(cid) == url}
        await self._prune_baselines()

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
                if "error" not in client_stats:
                    try:
                        await self._capture_baseline(client_id, client, client_stats)
                    except Exception as e:
                        logger.warning(f"Could not record the normal limits of {client_id}: {e}")
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
                        self._mark_written(client_name, client)
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
                        outcome, _ = await self._restore_one(client_name, client)
                        results[client_name] = outcome is RestoreOutcome.RESTORED

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

    def _with_upload(self, client_id: str) -> bool:
        cfg = self.client_configs.get(client_id)
        return True if cfg is None else bool(cfg.supports_upload)

    def _baseline_for(self, client_id: str, client: Any) -> Optional[Dict[str, float]]:
        """The limits a torrent client goes back to; None for clients that restore their own saved cap."""
        if getattr(client, "restores_saved_cap", False):
            return None
        return self._baselines.get(client_id)

    async def _restore_one(
        self, client_id: str, client: Any, retries: int = 3, retry_delay: float = 1.0
    ) -> Tuple[RestoreOutcome, Optional[Dict[str, float]]]:
        """Restore one client, retrying only on an exception (audit D3-3)."""
        baseline = self._baseline_for(client_id, client)
        if baseline is not None or getattr(client, "restores_saved_cap", False):
            self._mark_written(client_id, client)
        for attempt in range(1, retries + 1):
            try:
                limits = await client.restore_speed_limits(baseline)
            except Exception as e:
                if attempt < retries:
                    logger.warning(f"Failed to restore {client_id} (attempt {attempt}/{retries}): {e}")
                    await asyncio.sleep(retry_delay)
                    continue
                logger.error(f"Failed to restore {client_id} after {retries} attempts: {e}")
                return RestoreOutcome.FAILED, None
            if limits is None:
                logger.warning(f"Nothing to restore for {client_id}: Speedarr has never read its limits")
                return RestoreOutcome.NOTHING_TO_RESTORE, None
            logger.info(
                f"Restored {client_id} to its normal limits "
                f"({describe_limits(limits, self._with_upload(client_id))})"
            )
            return RestoreOutcome.RESTORED, limits
        return RestoreOutcome.FAILED, None

    async def restore_all_speeds(self, retries: int = 3, retry_delay: float = 1.0) -> Dict[str, RestoreOutcome]:
        """
        Put every client back to its normal limits in parallel, with retry on errors.

        Returns:
            Dict mapping client ids to what happened: restored, nothing to restore, or failed
        """
        if not self.clients:
            return {}

        async with self._write_lock:
            items = list(self.clients.items())
            pairs = await asyncio.gather(*[
                self._restore_one(client_id, client, retries, retry_delay)
                for client_id, client in items
            ])
        outcomes = {client_id: outcome for (client_id, _), (outcome, _) in zip(items, pairs)}
        logger.info(f"Restore finished: {restore_counts(outcomes)}")
        return outcomes

    async def remove_all_limits(self, retries: int = 3, retry_delay: float = 1.0) -> Dict[str, bool]:
        """
        Set every client to unlimited (issue #78 disable semantics).

        Unlike restore_all_speeds, this does not depend on any normal limit
        (a torrent client's recorded baseline or a usenet client's saved cap)
        - "disabled" means Speedarr leaves no limits behind.
        Each adapter's set_unlimited() maps to its native unlimited
        (qBittorrent 0, Transmission enabled=false, Deluge -1, SABnzbd 0
        written directly bypassing the issue-#43 floor, NZBGet 0).
        """
        async def remove_client_with_retry(name: str, client: Any) -> tuple[str, bool]:
            for attempt in range(1, retries + 1):
                self._mark_written(name, client)
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
            baseline = self._baseline_for(client_id, client)
            self._mark_written(client_id, client)
            for attempt in range(1, retries + 1):
                try:
                    # Restore first so unset directions return to normal speeds,
                    # then overlay the shutdown limits (None = leave unchanged)
                    restored = await client.restore_speed_limits(baseline)
                    if dl is not None or ul is not None:
                        await client.set_speed_limits(download_limit=dl, upload_limit=ul)
                    unset = "restored" if restored is not None else "nothing to restore"
                    logger.info(
                        f"Shutdown speeds applied to {client_id}: "
                        f"DL={f'{dl:.1f} Mbps' if dl is not None else unset}, "
                        f"UL={f'{ul:.1f} Mbps' if ul is not None else unset}"
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

