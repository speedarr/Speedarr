"""
Configuration management service.

Handles configuration updates, database storage, and service reloads.
"""
import logging
from typing import Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, and_

from app.config import (
    SpeedarrConfig,
    flatten_dict,
    unflatten_dict,
    serialize_value,
    deserialize_value,
    get_value_type,
    is_sensitive_key,
    encrypt_value,
    decrypt_value,
)
from app.models.configuration import Configuration, ConfigurationHistory

logger = logging.getLogger(__name__)


def validate_config(config: SpeedarrConfig) -> list[str]:
    """
    Validate configuration and return list of warnings.

    This doesn't prevent config from being used, but logs issues
    that might cause unexpected behavior.

    Returns:
        List of warning messages
    """
    warnings = []

    # Check bandwidth limits
    if config.bandwidth.download.total_limit <= 0:
        warnings.append(
            f"Download bandwidth limit is {config.bandwidth.download.total_limit} Mbps - "
            "this effectively disables download throttling"
        )
    elif config.bandwidth.download.total_limit < 10:
        warnings.append(
            f"Download bandwidth limit is very low ({config.bandwidth.download.total_limit} Mbps)"
        )

    if config.bandwidth.upload.total_limit <= 0:
        warnings.append(
            f"Upload bandwidth limit is {config.bandwidth.upload.total_limit} Mbps - "
            "this effectively disables upload throttling"
        )
    elif config.bandwidth.upload.total_limit < 10:
        warnings.append(
            f"Upload bandwidth limit is very low ({config.bandwidth.upload.total_limit} Mbps)"
        )

    # Check client percentages sum
    download_percents = config.bandwidth.download.client_percents
    if download_percents:
        total = sum(download_percents.values())
        if total > 100:
            warnings.append(
                f"Download client percentages sum to {total}% (>100%) - "
                "bandwidth will be over-allocated"
            )

    upload_percents = config.bandwidth.upload.upload_client_percents
    if upload_percents:
        total = sum(upload_percents.values())
        if total > 100:
            warnings.append(
                f"Upload client percentages sum to {total}% (>100%) - "
                "bandwidth will be over-allocated"
            )

    # Check protocol overhead
    overhead = config.bandwidth.streams.overhead_percent
    if overhead < 0:
        warnings.append(f"Protocol overhead is negative ({overhead}%) - using 0%")
    elif overhead > 300:
        warnings.append(f"Protocol overhead is very high ({overhead}%) - this triples stream bandwidth estimates")

    # Check failsafe timeout
    if config.failsafe.plex_timeout < 60:
        warnings.append(
            f"Plex failsafe timeout is very short ({config.failsafe.plex_timeout}s) - "
            "may cause frequent speed restorations during brief connectivity issues"
        )

    # Check polling frequency
    if config.system.update_frequency < 5:
        warnings.append(
            f"Polling frequency ({config.system.update_frequency}s) is below minimum - using 5s"
        )

    # Check for enabled clients without URL
    for client in config.get_enabled_download_clients():
        if not client.url:
            warnings.append(f"Download client '{client.name}' is enabled but has no URL configured")

    return warnings


class ConfigManager:
    """Manages configuration updates and service reloads."""

    def __init__(self, app):
        """Initialize ConfigManager with app instance."""
        self.app = app

    async def load_config_from_db(self, db: AsyncSession) -> Optional[SpeedarrConfig]:
        """
        Load configuration from database.

        Returns None if database is empty (not yet migrated).
        """
        # Check if migration has occurred
        result = await db.execute(
            select(Configuration).where(Configuration.key == "_migrated")
        )
        if not result.scalar_one_or_none():
            logger.info("Configuration not yet migrated to database")
            return None

        # Fetch all configuration rows
        result = await db.execute(select(Configuration))
        config_rows = result.scalars().all()

        if not config_rows:
            logger.warning("No configuration found in database")
            return None

        # Build nested dict from flat keys
        config_dict = {}
        for row in config_rows:
            # Skip internal keys
            if row.key.startswith("_"):
                continue

            # Deserialize value
            value = deserialize_value(row.value, row.value_type)

            # Handle "None" string from old data
            if row.value_type == "string" and value == "None":
                value = None

            # Decrypt if sensitive
            if is_sensitive_key(row.key) and row.value_type == "string" and value is not None:
                try:
                    value = decrypt_value(value)
                    # Handle "None" string from old migrations
                    if value == "None":
                        value = None
                except Exception as e:
                    # Fail fast on decryption errors - config is corrupted or encryption key changed
                    logger.error(f"Failed to decrypt config key '{row.key}': {e}")
                    raise ValueError(
                        f"Failed to decrypt configuration value '{row.key}'. "
                        "This usually means the CONFIG_ENCRYPTION_KEY has changed or the config is corrupted. "
                        "Check your encryption key or reset the affected settings."
                    ) from e

            config_dict[row.key] = value

        # Unflatten to nested structure
        nested_config = unflatten_dict(config_dict)

        # Handle migration: old history.retention_days was a dict, now it's a single int
        if "history" in nested_config and isinstance(nested_config["history"], dict):
            history_config = nested_config["history"]
            if "retention_days" in history_config and isinstance(history_config["retention_days"], dict):
                # Old format: {"streams": 90, "bandwidth": 90, "decisions": 60, "logs": 14}
                # New format: single integer (use the min of the old values, or default to 30)
                old_retention = history_config["retention_days"]
                retention_values = [v for v in old_retention.values() if isinstance(v, (int, float))]
                new_retention = int(min(retention_values)) if retention_values else 30
                logger.info(f"Migrating history.retention_days from dict to int: {new_retention}")
                history_config["retention_days"] = new_retention

        # Construct SpeedarrConfig from dict
        try:
            config = SpeedarrConfig(**nested_config)

            # Validate and log warnings
            warnings = validate_config(config)
            for warning in warnings:
                logger.warning(f"Config validation: {warning}")

            return config
        except Exception as e:
            logger.error(f"Failed to construct SpeedarrConfig from database: {e}")
            return None

    async def migrate_yaml_to_db(
        self, config: SpeedarrConfig, db: AsyncSession, user_id: Optional[int] = None
    ):
        """
        One-time migration from YAML to database.

        Args:
            config: SpeedarrConfig loaded from YAML
            db: Database session
            user_id: Optional user ID for audit trail
        """
        # Check if migration already done
        result = await db.execute(
            select(Configuration).where(Configuration.key == "_migrated")
        )
        if result.scalar_one_or_none():
            logger.info("Config already migrated to database")
            return

        logger.info("Migrating configuration from YAML to database...")

        # Flatten SpeedarrConfig to key-value pairs
        config_dict = config.model_dump()
        flat_config = flatten_dict(config_dict)

        # Store in database
        for key, value in flat_config.items():
            value_type = get_value_type(value)
            value_str = serialize_value(value, value_type)

            # Encrypt sensitive values (but not None/null values)
            if is_sensitive_key(key) and value_type == "string" and value is not None:
                value_str = encrypt_value(value_str)

            config_row = Configuration(
                key=key,
                value=value_str,
                value_type=value_type,
                description=None,  # Could extract from Field descriptions
                updated_by=user_id,
            )
            db.add(config_row)

        # Mark migration complete
        db.add(
            Configuration(
                key="_migrated",
                value="true",
                value_type="boolean",
                description="Migration from YAML complete",
                updated_by=user_id,
            )
        )

        await db.commit()
        logger.info(f"Config migrated: {len(flat_config)} settings stored in database")

    async def update_section(
        self,
        section_name: str,
        config_data: Dict[str, Any],
        db: AsyncSession,
        user_id: Optional[int] = None,
    ) -> SpeedarrConfig:
        """
        Update a configuration section.

        Args:
            section_name: Name of config section (e.g., "plex", "bandwidth")
            config_data: New configuration data for the section
            db: Database session
            user_id: User making the change (for audit trail)

        Returns:
            Updated SpeedarrConfig

        Raises:
            ValueError: If validation fails
        """
        logger.info(f"Updating config section: {section_name} by user {user_id}")

        # Clean up legacy keys for bandwidth section
        if section_name == "bandwidth":
            await self.cleanup_legacy_bandwidth_keys(db, user_id)

        # Flatten the section data
        flat_data = flatten_dict({section_name: config_data})

        # Update each key in database
        for key, value in flat_data.items():
            await self._update_key(key, value, db, user_id)

        await db.commit()

        # Reload config from database
        reloaded_config = await self.load_config_from_db(db)
        if not reloaded_config:
            raise ValueError("Failed to reload configuration from database")

        # Update app state
        self.app.state.config = reloaded_config

        # Reload affected services
        await self._reload_services(section_name, reloaded_config)

        logger.info(f"Config section '{section_name}' updated successfully")
        return reloaded_config

    async def _update_key(
        self, key: str, value: Any, db: AsyncSession, user_id: Optional[int]
    ):
        """Update a single configuration key."""
        # Skip update if value is the masked placeholder
        if is_sensitive_key(key) and value == "***REDACTED***":
            logger.debug(f"Skipping update for {key} - masked value detected")
            return

        # Handle None values by deleting the key
        if value is None:
            result = await db.execute(select(Configuration).where(Configuration.key == key))
            existing = result.scalar_one_or_none()
            if existing:
                await db.execute(delete(Configuration).where(Configuration.key == key))
                logger.debug(f"Deleted config key with None value: {key}")
            return

        value_type = get_value_type(value)
        value_str = serialize_value(value, value_type)


        # Encrypt sensitive values (but not None values)
        if is_sensitive_key(key) and value_type == "string" and value is not None:
            value_str = encrypt_value(value_str)

        # Get existing row
        result = await db.execute(select(Configuration).where(Configuration.key == key))
        existing = result.scalar_one_or_none()

        if existing:
            # Record old value in history
            history_entry = ConfigurationHistory(
                key=key,
                old_value=existing.value,
                new_value=value_str,
                value_type=value_type,
                changed_by=user_id,
            )
            db.add(history_entry)

            # Update existing
            existing.value = value_str
            existing.value_type = value_type
            existing.updated_by = user_id
        else:
            # Create new
            new_config = Configuration(
                key=key,
                value=value_str,
                value_type=value_type,
                updated_by=user_id,
            )
            db.add(new_config)

            # Record in history
            history_entry = ConfigurationHistory(
                key=key,
                old_value=None,
                new_value=value_str,
                value_type=value_type,
                changed_by=user_id,
            )
            db.add(history_entry)

    async def cleanup_legacy_bandwidth_keys(self, db: AsyncSession, user_id: Optional[int] = None):
        """
        Remove legacy bandwidth configuration keys from database.

        This cleans up old field names like:
        - bandwidth.download.standby_qbittorrent_percent
        - bandwidth.download.standby_sabnzbd_percent
        - bandwidth.download.both_active_qbittorrent_percent
        - bandwidth.download.both_active_sabnzbd_percent
        """
        legacy_keys = [
            "bandwidth.download.standby_qbittorrent_percent",
            "bandwidth.download.standby_sabnzbd_percent",
            "bandwidth.download.both_active_qbittorrent_percent",
            "bandwidth.download.both_active_sabnzbd_percent",
        ]

        for key in legacy_keys:
            result = await db.execute(select(Configuration).where(Configuration.key == key))
            existing = result.scalar_one_or_none()
            if existing:
                await db.execute(delete(Configuration).where(Configuration.key == key))
                logger.info(f"Cleaned up legacy bandwidth key: {key}")

                # Record in history
                history_entry = ConfigurationHistory(
                    key=key,
                    old_value=existing.value,
                    new_value="[DELETED]",
                    value_type=existing.value_type,
                    changed_by=user_id,
                )
                db.add(history_entry)

    async def _reload_services(self, section_name: str, config: SpeedarrConfig):
        """
        Reload services affected by config change.

        Args:
            section_name: Name of the config section that changed
            config: Updated configuration
        """
        logger.info(f"Reloading services affected by '{section_name}' change")

        try:
            if section_name == "plex":
                # Reload PollingMonitor Plex client
                if hasattr(self.app.state, "polling_monitor"):
                    from app.clients.plex import PlexClient

                    polling_monitor = self.app.state.polling_monitor
                    await polling_monitor.plex.close()
                    polling_monitor.plex = PlexClient(
                        url=config.plex.url,
                        token=config.plex.token
                    )
                    # Reset failure tracking so dashboard reflects new state
                    polling_monitor._plex_consecutive_failures = 0
                    polling_monitor._plex_unreachable_warned = False
                    logger.info("Plex client reloaded with updated config")

            elif section_name in ["qbittorrent", "sabnzbd", "transmission", "nzbget", "deluge"]:
                # Reload ControllerManager clients
                if hasattr(self.app.state, "controller_manager"):
                    controller_manager = self.app.state.controller_manager
                    await controller_manager.reload_clients(config)
                    logger.info("Download clients reloaded")

            elif section_name == "bandwidth":
                # Update DecisionEngine config
                if hasattr(self.app.state, "decision_engine"):
                    decision_engine = self.app.state.decision_engine
                    decision_engine.config = config
                    logger.info("DecisionEngine config updated")

            elif section_name == "notifications":
                # Reload NotificationService (needs full config, not just notifications section)
                if hasattr(self.app.state, "notification_service"):
                    notification_service = self.app.state.notification_service
                    notification_service.config = config
                    logger.info("NotificationService config updated")

            elif section_name == "system":
                # Update polling frequency - must update polling_monitor's config reference
                if hasattr(self.app.state, "polling_monitor"):
                    self.app.state.polling_monitor.config = config
                    logger.info(f"Polling monitor config updated, new frequency: {config.system.update_frequency}s")

            elif section_name == "snmp":
                # Reload SNMPMonitor
                if hasattr(self.app.state, "polling_monitor"):
                    self.app.state.polling_monitor.config = config
                    from app.services.snmp_monitor import SNMPMonitor

                    if config.snmp.enabled:
                        # Create new SNMPMonitor with updated config
                        self.app.state.polling_monitor.snmp_monitor = SNMPMonitor(
                            config.snmp
                        )
                        logger.info("SNMPMonitor reloaded with updated config")
                    else:
                        # Disable SNMP monitoring
                        self.app.state.polling_monitor.snmp_monitor = None
                        logger.info("SNMPMonitor disabled")

        except Exception as e:
            logger.error(f"Error reloading services for section '{section_name}': {e}")
            # Don't raise - config is already saved, service reload is best-effort

    async def update_full_config(
        self,
        config_data: Dict[str, Any],
        db: AsyncSession,
        user_id: Optional[int] = None,
    ) -> SpeedarrConfig:
        """
        Update the entire configuration.

        This is used for operations that need to modify the config structure,
        like switching from legacy single-client configs to the new download_clients list.

        Args:
            config_data: Complete new configuration data
            db: Database session
            user_id: User making the change (for audit trail)

        Returns:
            Updated SpeedarrConfig

        Raises:
            ValueError: If validation fails
        """
        logger.info(f"Updating full config by user {user_id}")

        # Validate the new config by constructing it
        try:
            new_config = SpeedarrConfig(**config_data)
        except Exception as e:
            raise ValueError(f"Invalid configuration: {e}")

        # Clear existing config keys that are no longer valid
        # This handles removal of legacy configs

        # Get all current keys
        result = await db.execute(select(Configuration).where(~Configuration.key.startswith("_")))
        existing_keys = {row.key for row in result.scalars().all()}

        # Flatten new config
        flat_config = flatten_dict(config_data)
        new_keys = set(flat_config.keys())

        # Remove keys that are no longer in the config
        keys_to_remove = existing_keys - new_keys
        for key in keys_to_remove:
            if not key.startswith("_"):
                await db.execute(delete(Configuration).where(Configuration.key == key))
                logger.debug(f"Removed config key: {key}")

        # Update or insert all new config keys
        for key, value in flat_config.items():
            await self._update_key(key, value, db, user_id)

        await db.commit()

        # Reload config from database
        reloaded_config = await self.load_config_from_db(db)
        if not reloaded_config:
            raise ValueError("Failed to reload configuration from database")

        # Update app state
        self.app.state.config = reloaded_config

        # Reload download clients (skip during setup mode when controller_manager is None)
        if hasattr(self.app.state, "controller_manager") and self.app.state.controller_manager is not None:
            controller_manager = self.app.state.controller_manager
            await controller_manager.reload_clients(reloaded_config)
            logger.info("Download clients reloaded after full config update")

        logger.info("Full config updated successfully")
        return reloaded_config

    async def export_to_yaml(self, db: AsyncSession) -> Dict[str, Any]:
        """
        Export current configuration from database to YAML-compatible dict.

        Returns:
            Nested dictionary suitable for YAML export
        """
        config = await self.load_config_from_db(db)
        if not config:
            raise ValueError("No configuration found in database")

        return config.model_dump()

    def _values_are_different(self, old_value: str, new_value: str) -> bool:
        """Check if two values are actually different (handles numeric comparison)."""
        if old_value is None:
            return True
        if old_value == new_value:
            return False

        # Try numeric comparison (handles "60.0" vs "60")
        try:
            old_num = float(old_value)
            new_num = float(new_value)
            return old_num != new_num
        except (ValueError, TypeError):
            pass

        return old_value != new_value

    async def get_config_history(
        self, db: AsyncSession, key: Optional[str] = None, limit: int = 100,
        only_changed: bool = False
    ) -> list:
        """
        Get configuration change history.

        Args:
            db: Database session
            key: Optional key to filter by
            limit: Maximum number of entries to return
            only_changed: If True, only return entries where values actually changed

        Returns:
            List of history entries
        """
        query = select(ConfigurationHistory).order_by(
            ConfigurationHistory.changed_at.desc()
        )

        if key:
            query = query.where(ConfigurationHistory.key == key)

        if only_changed:
            # Fetch more entries to ensure we get enough after filtering
            # We fetch 5x the limit to account for unchanged entries
            query = query.limit(limit * 5)
            result = await db.execute(query)
            all_entries = result.scalars().all()

            # Filter to only entries where values actually changed
            changed_entries = [
                entry for entry in all_entries
                if self._values_are_different(entry.old_value, entry.new_value)
            ]
            return changed_entries[:limit]
        else:
            query = query.limit(limit)
            result = await db.execute(query)
            return result.scalars().all()
