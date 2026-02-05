"""
Controller manager for applying throttling decisions to download clients.
"""
import asyncio
from typing import Dict, Any, Optional
from loguru import logger
from app.clients import QBittorrentClient, SABnzbdClient, create_download_client
from app.config import SpeedarrConfig


class ControllerManager:
    """
    Manages download clients and applies throttling decisions.
    """

    def __init__(self, config: SpeedarrConfig):
        self.config = config
        self.clients: Dict[str, Any] = {}  # client_id -> client instance
        self.client_configs: Dict[str, Any] = {}  # client_id -> client config (for type, name lookup)
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

    async def apply_decisions(self, decisions: Dict[str, Dict[str, Any]]) -> Dict[str, bool]:
        """
        Apply throttling decisions to download clients.

        Args:
            decisions: Dict mapping client names to decision dicts

        Returns:
            Dict mapping client names to success status
        """
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

        results_list = await asyncio.gather(*[
            restore_client_with_retry(name, client)
            for name, client in self.clients.items()
        ])
        return dict(results_list)

