"""
Settings API endpoints.
"""
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
import yaml
from loguru import logger

from app.database import get_db
from app.api.auth import get_current_user
from app.models.user import User
from app.services.config_manager import ConfigManager
from app.config import SpeedarrConfig, DownloadClientConfig

router = APIRouter(prefix="/api/settings", tags=["settings"])


class SectionMetadata(BaseModel):
    """Metadata about a configuration section."""

    id: str
    name: str
    description: str
    icon: str
    requires_restart: bool = False
    requires_test: bool = False


class SectionResponse(BaseModel):
    """Response for a configuration section."""

    section: str
    config: Dict[str, Any]


class SettingsUpdateRequest(BaseModel):
    """Request to update settings section."""

    config: Dict[str, Any]


class TestConnectionRequest(BaseModel):
    """Request to test service connection."""

    config: Dict[str, Any]
    use_existing: bool = False  # If True, use the saved config instead of provided values


class TestConnectionResponse(BaseModel):
    """Response from connection test."""

    success: bool
    message: str
    details: Optional[Dict[str, Any]] = None


class HistoryEntry(BaseModel):
    """Configuration change history entry."""

    key: str
    old_value: Optional[str]
    new_value: str
    value_type: str
    changed_at: str
    changed_by: Optional[int]


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Dependency to require admin role."""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required"
        )
    return current_user


@router.get("/sections", response_model=Dict[str, List[SectionMetadata]])
async def get_sections():
    """Get metadata about all configuration sections."""
    sections = [
        SectionMetadata(
            id="system",
            name="System Settings",
            description="Core system configuration",
            icon="settings",
            requires_restart=False,
            requires_test=False,
        ),
        SectionMetadata(
            id="plex",
            name="Plex",
            description="Plex Media Server connection",
            icon="server",
            requires_restart=False,
            requires_test=True,
        ),
        SectionMetadata(
            id="qbittorrent",
            name="qBittorrent",
            description="qBittorrent download client",
            icon="download",
            requires_restart=False,
            requires_test=True,
        ),
        SectionMetadata(
            id="sabnzbd",
            name="SABnzbd",
            description="SABnzbd download client",
            icon="download",
            requires_restart=False,
            requires_test=True,
        ),
        SectionMetadata(
            id="snmp",
            name="SNMP Monitoring",
            description="Network monitoring via SNMP",
            icon="activity",
            requires_restart=False,
            requires_test=False,
        ),
        SectionMetadata(
            id="bandwidth",
            name="Bandwidth Management",
            description="Download/Upload limits and allocation",
            icon="gauge",
            requires_restart=False,
            requires_test=False,
        ),
        SectionMetadata(
            id="restoration",
            name="Restoration Delays",
            description="Speed restoration timing",
            icon="clock",
            requires_restart=False,
            requires_test=False,
        ),
        SectionMetadata(
            id="notifications",
            name="Notifications",
            description="Discord and webhook notifications",
            icon="bell",
            requires_restart=False,
            requires_test=True,
        ),
        SectionMetadata(
            id="history",
            name="Data Retention",
            description="Historical data retention settings",
            icon="database",
            requires_restart=False,
            requires_test=False,
        ),
        SectionMetadata(
            id="failsafe",
            name="Failsafe",
            description="Timeout and alert settings",
            icon="shield",
            requires_restart=False,
            requires_test=False,
        ),
    ]

    return {"sections": sections}


@router.get("/section/{section_name}", response_model=SectionResponse)
async def get_section(section_name: str, request: Request):
    """Get configuration for a specific section."""
    config: SpeedarrConfig = request.app.state.config

    # Handle setup mode where config is None - return default values
    if config is None:
        from app.config import (
            SystemConfig, PlexConfig, SNMPConfig, BandwidthConfig,
            RestorationConfig, NotificationsConfig, HistoryConfig, FailsafeConfig
        )
        defaults = {
            "system": SystemConfig(),
            "plex": PlexConfig(),
            "snmp": SNMPConfig(),
            "bandwidth": BandwidthConfig(total_download_mbps=100, total_upload_mbps=100),
            "restoration": RestorationConfig(),
            "notifications": NotificationsConfig(),
            "history": HistoryConfig(),
            "failsafe": FailsafeConfig(),
        }
        if section_name in defaults:
            section_config = defaults[section_name].model_dump()
            masked_config = _mask_sensitive_values(section_config)
            return SectionResponse(section=section_name, config=masked_config)
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Section '{section_name}' not found",
            )

    # Get section config
    section_config = None
    if hasattr(config, section_name):
        section_obj = getattr(config, section_name)
        if hasattr(section_obj, "model_dump"):
            section_config = section_obj.model_dump()
        elif isinstance(section_obj, dict):
            section_config = section_obj
    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Section '{section_name}' not found",
        )

    # Mask sensitive values
    masked_config = _mask_sensitive_values(section_config)

    return SectionResponse(section=section_name, config=masked_config)


@router.put("/section/{section_name}", response_model=SectionResponse)
async def update_section(
    section_name: str,
    update_request: SettingsUpdateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Update a configuration section.

    Requires admin role. Validates, saves to database, and reloads affected services.
    """
    # Get ConfigManager from app state
    if not hasattr(request.app.state, "config_manager"):
        request.app.state.config_manager = ConfigManager(request.app)

    config_manager: ConfigManager = request.app.state.config_manager

    try:
        # Update section
        updated_config = await config_manager.update_section(
            section_name=section_name,
            config_data=update_request.config,
            db=db,
            user_id=current_user.id,
        )

        # Get updated section
        section_obj = getattr(updated_config, section_name)
        section_config = (
            section_obj.model_dump()
            if hasattr(section_obj, "model_dump")
            else section_obj
        )

        # Mask sensitive values
        masked_config = _mask_sensitive_values(section_config)

        return SectionResponse(section=section_name, config=masked_config)

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update configuration: {str(e)}",
        )


@router.post("/test/{service}", response_model=TestConnectionResponse)
async def test_connection(
    service: str,
    test_request: TestConnectionRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
):
    """
    Test connection to a service with provided config.

    Does not save to database - just tests the connection.
    If use_existing is True, uses the saved config for sensitive values.
    """
    config_data = test_request.config
    app_config: SpeedarrConfig = request.app.state.config

    try:
        if service == "plex":
            from app.clients.plex import PlexClient

            url = config_data.get("url") or app_config.plex.url
            token = config_data.get("token")

            # If use_existing or token is masked, use the saved config
            if test_request.use_existing or token == "***REDACTED***":
                if app_config.plex.token:
                    token = app_config.plex.token
                else:
                    return TestConnectionResponse(
                        success=False,
                        message="No Plex token configured. Please enter a token.",
                    )

            if not url or not token:
                return TestConnectionResponse(
                    success=False, message="Missing required fields: url and token"
                )

            client = PlexClient(url=url, token=token)
            success = await client.test_connection()
            await client.close()

            if success:
                return TestConnectionResponse(
                    success=True, message="Successfully connected to Plex"
                )
            else:
                return TestConnectionResponse(
                    success=False,
                    message="Failed to connect to Plex. Check URL and token.",
                )

        elif service == "qbittorrent":
            from app.clients.qbittorrent import QBittorrentClient

            url = config_data.get("url") or app_config.qbittorrent.url
            username = config_data.get("username") or app_config.qbittorrent.username
            password = config_data.get("password")

            # If use_existing or password is masked, use the saved config
            if test_request.use_existing or password == "***REDACTED***":
                password = app_config.qbittorrent.password

            if not url or not username or not password:
                return TestConnectionResponse(
                    success=False,
                    message="Missing required fields: url, username, and password",
                )

            client = QBittorrentClient(url=url, username=username, password=password)
            success = await client.test_connection()
            await client.close()

            if success:
                return TestConnectionResponse(
                    success=True, message="Successfully connected to qBittorrent"
                )
            else:
                return TestConnectionResponse(
                    success=False,
                    message="Failed to connect to qBittorrent. Check URL and credentials.",
                )

        elif service == "sabnzbd":
            from app.clients.sabnzbd import SABnzbdClient

            url = config_data.get("url") or app_config.sabnzbd.url
            api_key = config_data.get("api_key")

            # If use_existing or api_key is masked, use the saved config
            if test_request.use_existing or api_key == "***REDACTED***":
                if app_config.sabnzbd.api_key:
                    api_key = app_config.sabnzbd.api_key
                else:
                    return TestConnectionResponse(
                        success=False,
                        message="No SABnzbd API key configured. Please enter an API key.",
                    )

            if not url or not api_key:
                return TestConnectionResponse(
                    success=False, message="Missing required fields: url and api_key"
                )

            client = SABnzbdClient(url=url, api_key=api_key)
            success = await client.test_connection()
            await client.close()

            if success:
                return TestConnectionResponse(
                    success=True, message="Successfully connected to SABnzbd"
                )
            else:
                return TestConnectionResponse(
                    success=False,
                    message="Failed to connect to SABnzbd. Check URL and API key.",
                )

        elif service == "nzbget":
            from app.clients.nzbget import NZBGetClient

            url = config_data.get("url", "")
            username = config_data.get("username", "")
            password = config_data.get("password", "")

            # Get existing client config for use_existing
            if test_request.use_existing or password == "***REDACTED***":
                existing = _find_existing_client(app_config, config_data.get("id"), "nzbget")
                if existing and existing.password:
                    password = existing.password
                elif password == "***REDACTED***":
                    return TestConnectionResponse(
                        success=False,
                        message="No NZBGet password configured. Please enter a password.",
                    )

            if not url:
                return TestConnectionResponse(
                    success=False, message="Missing required field: url"
                )

            client = NZBGetClient(
                client_id=config_data.get("id", "nzbget"),
                name=config_data.get("name", "NZBGet"),
                url=url,
                username=username,
                password=password
            )
            success = await client.test_connection()
            await client.close()

            if success:
                return TestConnectionResponse(
                    success=True, message="Successfully connected to NZBGet"
                )
            else:
                return TestConnectionResponse(
                    success=False,
                    message="Failed to connect to NZBGet. Check URL and credentials.",
                )

        elif service == "transmission":
            from app.clients.transmission import TransmissionClient

            url = config_data.get("url", "")
            username = config_data.get("username", "")
            password = config_data.get("password", "")

            # Get existing client config for use_existing
            if test_request.use_existing or password == "***REDACTED***":
                existing = _find_existing_client(app_config, config_data.get("id"), "transmission")
                if existing and existing.password:
                    password = existing.password
                elif password == "***REDACTED***":
                    return TestConnectionResponse(
                        success=False,
                        message="No Transmission password configured. Please enter a password.",
                    )

            if not url:
                return TestConnectionResponse(
                    success=False, message="Missing required field: url"
                )

            client = TransmissionClient(
                client_id=config_data.get("id", "transmission"),
                name=config_data.get("name", "Transmission"),
                url=url,
                username=username,
                password=password
            )
            success = await client.test_connection()
            await client.close()

            if success:
                return TestConnectionResponse(
                    success=True, message="Successfully connected to Transmission"
                )
            else:
                return TestConnectionResponse(
                    success=False,
                    message="Failed to connect to Transmission. Check URL and credentials.",
                )

        elif service == "deluge":
            from app.clients.deluge import DelugeClient

            url = config_data.get("url", "")
            password = config_data.get("password", "")

            # Get existing client config for use_existing
            if test_request.use_existing or password == "***REDACTED***":
                existing = _find_existing_client(app_config, config_data.get("id"), "deluge")
                if existing and existing.password:
                    password = existing.password
                elif password == "***REDACTED***":
                    return TestConnectionResponse(
                        success=False,
                        message="No Deluge password configured. Please enter a password.",
                    )

            if not url or not password:
                return TestConnectionResponse(
                    success=False, message="Missing required fields: url and password"
                )

            client = DelugeClient(
                client_id=config_data.get("id", "deluge"),
                name=config_data.get("name", "Deluge"),
                url=url,
                password=password
            )
            success = await client.test_connection()
            await client.close()

            if success:
                return TestConnectionResponse(
                    success=True, message="Successfully connected to Deluge"
                )
            else:
                return TestConnectionResponse(
                    success=False,
                    message="Failed to connect to Deluge. Check URL and password.",
                )

        elif service == "discord":
            import aiohttp

            webhook_url = config_data.get("webhook_url")

            # If use_existing or URL is masked, use the saved config
            if test_request.use_existing or webhook_url == "***REDACTED***":
                if app_config.notifications.discord.webhook_url:
                    webhook_url = app_config.notifications.discord.webhook_url
                else:
                    return TestConnectionResponse(
                        success=False,
                        message="No Discord webhook URL configured. Please enter a webhook URL.",
                    )

            if not webhook_url:
                return TestConnectionResponse(
                    success=False, message="Missing required field: webhook_url"
                )

            # Send a test message to Discord webhook
            async with aiohttp.ClientSession() as session:
                payload = {
                    "content": "Speedarr connection test - webhook is working correctly!"
                }
                async with session.post(
                    webhook_url, json=payload, timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status in (200, 204):
                        return TestConnectionResponse(
                            success=True,
                            message="Successfully sent test message to Discord webhook",
                        )
                    else:
                        return TestConnectionResponse(
                            success=False,
                            message=f"Discord webhook returned status {response.status}",
                        )

        elif service == "pushover":
            import aiohttp

            user_key = config_data.get("user_key")
            api_token = config_data.get("api_token")

            # If use_existing or values are masked, use the saved config
            if test_request.use_existing or user_key == "***REDACTED***":
                if app_config.notifications.pushover.user_key:
                    user_key = app_config.notifications.pushover.user_key
            if test_request.use_existing or api_token == "***REDACTED***":
                if app_config.notifications.pushover.api_token:
                    api_token = app_config.notifications.pushover.api_token

            if not user_key or not api_token:
                return TestConnectionResponse(
                    success=False, message="Missing required fields: user_key and api_token"
                )

            # Send a test message to Pushover
            async with aiohttp.ClientSession() as session:
                payload = {
                    "token": api_token,
                    "user": user_key,
                    "title": "Speedarr Test",
                    "message": "Pushover notification is working correctly!",
                }
                async with session.post(
                    "https://api.pushover.net/1/messages.json",
                    data=payload,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        return TestConnectionResponse(
                            success=True,
                            message="Successfully sent test message to Pushover",
                        )
                    else:
                        text = await response.text()
                        return TestConnectionResponse(
                            success=False,
                            message=f"Pushover returned status {response.status}: {text}",
                        )

        elif service == "telegram":
            import aiohttp

            bot_token = config_data.get("bot_token")
            chat_id = config_data.get("chat_id")

            # If use_existing or values are masked, use the saved config
            if test_request.use_existing or bot_token == "***REDACTED***":
                if app_config.notifications.telegram.bot_token:
                    bot_token = app_config.notifications.telegram.bot_token
            if test_request.use_existing or chat_id == "***REDACTED***":
                if app_config.notifications.telegram.chat_id:
                    chat_id = app_config.notifications.telegram.chat_id

            if not bot_token or not chat_id:
                return TestConnectionResponse(
                    success=False, message="Missing required fields: bot_token and chat_id"
                )

            # Send a test message to Telegram
            async with aiohttp.ClientSession() as session:
                url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
                payload = {
                    "chat_id": chat_id,
                    "text": "<b>Speedarr Test</b>\nTelegram notification is working correctly!",
                    "parse_mode": "HTML",
                }
                async with session.post(
                    url, json=payload, timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        return TestConnectionResponse(
                            success=True,
                            message="Successfully sent test message to Telegram",
                        )
                    else:
                        text = await response.text()
                        return TestConnectionResponse(
                            success=False,
                            message=f"Telegram returned status {response.status}: {text}",
                        )

        elif service == "gotify":
            import aiohttp

            server_url = config_data.get("server_url")
            app_token = config_data.get("app_token")

            # If use_existing or values are masked, use the saved config
            if test_request.use_existing or app_token == "***REDACTED***":
                if app_config.notifications.gotify.app_token:
                    app_token = app_config.notifications.gotify.app_token
            if not server_url:
                server_url = app_config.notifications.gotify.server_url

            if not server_url or not app_token:
                return TestConnectionResponse(
                    success=False, message="Missing required fields: server_url and app_token"
                )

            # Send a test message to Gotify
            async with aiohttp.ClientSession() as session:
                url = f"{server_url.rstrip('/')}/message"
                payload = {
                    "title": "Speedarr Test",
                    "message": "Gotify notification is working correctly!",
                    "priority": 5,
                }
                headers = {"X-Gotify-Key": app_token}
                async with session.post(
                    url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        return TestConnectionResponse(
                            success=True,
                            message="Successfully sent test message to Gotify",
                        )
                    else:
                        text = await response.text()
                        return TestConnectionResponse(
                            success=False,
                            message=f"Gotify returned status {response.status}: {text}",
                        )

        elif service == "ntfy":
            import aiohttp

            server_url = config_data.get("server_url", "https://ntfy.sh")
            topic = config_data.get("topic")

            if not topic:
                return TestConnectionResponse(
                    success=False, message="Missing required field: topic"
                )

            # Send a test message to ntfy
            async with aiohttp.ClientSession() as session:
                url = f"{server_url.rstrip('/')}/{topic}"
                headers = {
                    "Title": "Speedarr Test",
                    "Priority": "3",
                }
                async with session.post(
                    url, data="ntfy notification is working correctly!",
                    headers=headers, timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        return TestConnectionResponse(
                            success=True,
                            message="Successfully sent test message to ntfy",
                        )
                    else:
                        text = await response.text()
                        return TestConnectionResponse(
                            success=False,
                            message=f"ntfy returned status {response.status}: {text}",
                        )

        elif service == "snmp":
            from app.services.snmp_monitor import SNMPMonitor
            from app.config import SNMPConfig

            # Build SNMP config from test data
            try:
                snmp_config = SNMPConfig(**config_data)
            except Exception as e:
                return TestConnectionResponse(
                    success=False, message=f"Invalid SNMP configuration: {str(e)}"
                )

            # Check for masked passwords
            if snmp_config.version == "v3":
                if (
                    snmp_config.auth_protocol != "none"
                    and snmp_config.auth_password == "***REDACTED***"
                ):
                    return TestConnectionResponse(
                        success=False,
                        message="Cannot test with masked auth password. Please enter the actual password.",
                    )
                if (
                    snmp_config.priv_protocol != "none"
                    and snmp_config.priv_password == "***REDACTED***"
                ):
                    return TestConnectionResponse(
                        success=False,
                        message="Cannot test with masked priv password. Please enter the actual password.",
                    )
            elif snmp_config.community == "***REDACTED***":
                return TestConnectionResponse(
                    success=False,
                    message="Cannot test with masked community string. Please enter the actual value.",
                )

            monitor = SNMPMonitor(snmp_config)
            success = await monitor.test_connection()
            await monitor.close()

            if success:
                return TestConnectionResponse(
                    success=True, message="Successfully connected to SNMP device"
                )
            else:
                return TestConnectionResponse(
                    success=False,
                    message="Failed to connect to SNMP device. Check host, port, and credentials.",
                )

        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown service: {service}",
            )

    except Exception as e:
        logger.error(f"Connection test failed for {service}: {e}")
        return TestConnectionResponse(
            success=False, message=f"Connection test failed: {str(e)}"
        )


@router.post("/reload")
async def reload_services(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Force reload all services with current configuration."""
    config: SpeedarrConfig = request.app.state.config

    results = {}

    # Reload download clients
    if hasattr(request.app.state, "controller_manager"):
        controller_manager = request.app.state.controller_manager
        client_results = await controller_manager.reload_clients(config)
        results["clients"] = client_results

    return {"success": True, "results": results}


@router.post("/initialize-config")
async def initialize_config(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Initialize default configuration for fresh setup.

    Creates a default SpeedarrConfig in the database with the _migrated flag,
    allowing subsequent updateSettingsSection calls to work properly.
    """
    from sqlalchemy import select
    from app.models.configuration import Configuration
    from app.config import (
        PlexConfig, BandwidthConfig, DownloadBandwidthConfig,
        UploadBandwidthConfig, StreamBandwidthConfig
    )

    config_manager: ConfigManager = request.app.state.config_manager

    # Check if already initialized
    result = await db.execute(
        select(Configuration).where(Configuration.key == "_migrated")
    )
    if result.scalar_one_or_none():
        return {"success": True, "message": "Configuration already initialized"}

    # Create default config with placeholder values
    # These will be overwritten by the wizard's actual settings
    default_config = SpeedarrConfig(
        plex=PlexConfig(
            url="http://localhost:32400",
            token="placeholder",
        ),
        bandwidth=BandwidthConfig(
            download=DownloadBandwidthConfig(
                total_limit=100.0,
                client_percents={},
                inactive_safety_net_percent=5,
            ),
            upload=UploadBandwidthConfig(
                total_limit=20.0,
                upload_client_percents={},
            ),
            streams=StreamBandwidthConfig(),
        ),
    )

    # Use migrate_yaml_to_db to properly initialize the database
    await config_manager.migrate_yaml_to_db(default_config, db, current_user.id)
    await db.commit()

    logger.info("Default configuration initialized for fresh setup")
    return {"success": True, "message": "Configuration initialized successfully"}


@router.post("/complete-setup")
async def complete_setup(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Complete initial setup and initialize all services.

    Called after the setup wizard finishes to:
    1. Load configuration from database
    2. Initialize all services
    3. Clear setup_required flag
    """
    from app.services import DecisionEngine, ControllerManager, PollingMonitor, NotificationService
    from app.database import AsyncSessionLocal

    config_manager: ConfigManager = request.app.state.config_manager

    # Load configuration from database
    config = await config_manager.load_config_from_db(db)
    if not config:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Configuration is incomplete. Please complete all required setup steps.",
        )

    try:
        # Stop existing polling monitor if running
        if hasattr(request.app.state, "polling_monitor") and request.app.state.polling_monitor:
            try:
                await request.app.state.polling_monitor.stop()
            except Exception as e:
                logger.warning(f"Error stopping existing polling monitor: {e}")

        # Initialize services
        decision_engine = DecisionEngine(config)
        controller_manager = ControllerManager(config)
        notification_service = NotificationService(config)

        # Test client connections
        logger.info("Testing download client connections...")
        connection_results = await controller_manager.test_connections()
        for client, conn_status in connection_results.items():
            if conn_status:
                logger.info(f"✓ {client} connected")
            else:
                logger.warning(f"✗ {client} connection failed")

        # Start polling monitor
        polling_monitor = PollingMonitor(
            config,
            decision_engine,
            controller_manager,
            AsyncSessionLocal,
            notification_service
        )
        await polling_monitor.start()

        # Store services in app state
        request.app.state.decision_engine = decision_engine
        request.app.state.controller_manager = controller_manager
        request.app.state.polling_monitor = polling_monitor
        request.app.state.notification_service = notification_service
        request.app.state.plex_client = polling_monitor.plex
        request.app.state.config = config
        request.app.state.setup_required = False

        logger.info("Setup completed successfully - Speedarr is now running")

        return {"success": True, "message": "Setup completed successfully"}

    except Exception as e:
        logger.error(f"Failed to complete setup: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initialize services: {str(e)}",
        )


@router.get("/gather-logs")
async def gather_logs(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    """
    Gather application logs with sensitive data redacted.

    Returns recent log content with passwords, API keys, tokens, and webhook URLs
    replaced with [REDACTED] to allow safe sharing for debugging.
    """
    import os
    import re
    from pathlib import Path

    # Log file locations to check
    log_paths = [
        Path("/data/logs/speedarr.log"),
        Path("/data/speedarr.log"),
        Path("./logs/speedarr.log"),
        Path("./speedarr.log"),
    ]

    # Find the first existing log file
    log_file = None
    for path in log_paths:
        if path.exists():
            log_file = path
            break

    if not log_file:
        # Return empty log with info message
        return {
            "logs": "No log file found. Logs may be output to stdout in Docker.\n"
                    "Check your Docker container logs using: docker logs <container_name>"
        }

    try:
        # Read log file (last 10000 lines max)
        with open(log_file, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()
            # Keep last 10000 lines to limit file size
            lines = lines[-10000:]
            log_content = ''.join(lines)
    except Exception as e:
        return {"logs": f"Error reading log file: {str(e)}"}

    # Patterns to redact sensitive data
    redaction_patterns = [
        # API keys and tokens
        (r'(api_key["\']?\s*[:=]\s*["\']?)[^"\'\s,}\]]+', r'\1[REDACTED]'),
        (r'(api-key["\']?\s*[:=]\s*["\']?)[^"\'\s,}\]]+', r'\1[REDACTED]'),
        (r'(apikey["\']?\s*[:=]\s*["\']?)[^"\'\s,}\]]+', r'\1[REDACTED]'),
        (r'(token["\']?\s*[:=]\s*["\']?)[^"\'\s,}\]]+', r'\1[REDACTED]'),
        (r'(secret["\']?\s*[:=]\s*["\']?)[^"\'\s,}\]]+', r'\1[REDACTED]'),
        # Passwords
        (r'(password["\']?\s*[:=]\s*["\']?)[^"\'\s,}\]]+', r'\1[REDACTED]'),
        (r'(passwd["\']?\s*[:=]\s*["\']?)[^"\'\s,}\]]+', r'\1[REDACTED]'),
        # Webhook URLs (Discord, Teams, Slack patterns)
        (r'(https://discord\.com/api/webhooks/)[^\s"\']+', r'\1[REDACTED]'),
        (r'(https://discordapp\.com/api/webhooks/)[^\s"\']+', r'\1[REDACTED]'),
        (r'(https://[^/]*\.webhook\.office\.com/)[^\s"\']+', r'\1[REDACTED]'),
        (r'(https://hooks\.slack\.com/)[^\s"\']+', r'\1[REDACTED]'),
        # Generic webhook URLs with tokens
        (r'(webhook_url["\']?\s*[:=]\s*["\']?)[^"\'\s,}\]]+', r'\1[REDACTED]'),
        # Authorization headers
        (r'(Authorization["\']?\s*[:=]\s*["\']?)[^"\'\s,}\]]+', r'\1[REDACTED]'),
        (r'(Bearer\s+)[^\s"\']+', r'\1[REDACTED]'),
    ]

    # Apply all redaction patterns
    redacted_content = log_content
    for pattern, replacement in redaction_patterns:
        redacted_content = re.sub(pattern, replacement, redacted_content, flags=re.IGNORECASE)

    return {"logs": redacted_content}


@router.get("/export")
async def export_config(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Export current configuration as YAML."""
    if not hasattr(request.app.state, "config_manager"):
        request.app.state.config_manager = ConfigManager(request.app)

    config_manager: ConfigManager = request.app.state.config_manager

    try:
        config_dict = await config_manager.export_to_yaml(db)
        yaml_content = yaml.dump(config_dict, default_flow_style=False, sort_keys=False)

        return {
            "yaml": yaml_content,
            "config": config_dict,
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to export configuration: {str(e)}",
        )


@router.get("/history", response_model=List[HistoryEntry])
async def get_history(
    key: Optional[str] = None,
    limit: int = 100,
    only_changed: bool = False,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Get configuration change history.

    Args:
        key: Optional key to filter by
        limit: Maximum number of entries to return
        only_changed: If True, only return entries where values actually changed
    """
    if not hasattr(request.app.state, "config_manager"):
        request.app.state.config_manager = ConfigManager(request.app)

    config_manager: ConfigManager = request.app.state.config_manager

    history = await config_manager.get_config_history(
        db, key=key, limit=limit, only_changed=only_changed
    )

    return [
        HistoryEntry(
            key=entry.key,
            old_value=entry.old_value,
            new_value=entry.new_value,
            value_type=entry.value_type,
            changed_at=entry.changed_at.isoformat(),
            changed_by=entry.changed_by,
        )
        for entry in history
    ]


@router.post("/snmp/discover")
async def discover_snmp_interfaces(
    test_request: TestConnectionRequest,
    current_user: User = Depends(require_admin),
):
    """
    Discover network interfaces on SNMP device.

    Used during SNMP setup to show user available interfaces and suggest WAN.
    """
    from app.services.snmp_monitor import SNMPMonitor
    from app.config import SNMPConfig

    config_data = test_request.config

    try:
        # Build SNMP config from test data
        try:
            snmp_config = SNMPConfig(**config_data)
        except Exception as e:
            return {
                "success": False,
                "message": f"Invalid SNMP configuration: {str(e)}",
                "interfaces": [],
                "suggested_wan": None,
            }

        # Create monitor and discover interfaces
        monitor = SNMPMonitor(snmp_config)
        interfaces = await monitor.discover_interfaces()
        await monitor.close()

        if not interfaces:
            return {
                "success": False,
                "message": "No interfaces discovered. Check SNMP credentials and device access.",
                "interfaces": [],
                "suggested_wan": None,
            }

        # Suggest WAN interface
        suggested = monitor.suggest_wan_interface(interfaces)

        # Convert interfaces to dict format
        interfaces_data = []
        for iface in interfaces:
            iface_dict = iface.to_dict()
            # Mark suggested WAN interface
            if suggested and iface.index == suggested.index:
                iface_dict["is_wan_candidate"] = True
            interfaces_data.append(iface_dict)

        return {
            "success": True,
            "message": f"Discovered {len(interfaces)} interfaces",
            "interfaces": interfaces_data,
            "suggested_wan": str(suggested.index) if suggested else None,
        }

    except Exception as e:
        from loguru import logger

        logger.error(f"SNMP interface discovery failed: {e}")
        return {
            "success": False,
            "message": f"Interface discovery failed: {str(e)}",
            "interfaces": [],
            "suggested_wan": None,
        }


class PollSpeedsRequest(BaseModel):
    """Request to poll current speeds for interfaces."""

    config: Dict[str, Any]
    interface_indices: List[int]


@router.post("/snmp/poll-speeds")
async def poll_snmp_speeds(
    request: PollSpeedsRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Poll current speeds for specific interfaces.

    Uses self-contained measurement (two samples with delay).
    """
    from app.services.snmp_monitor import SNMPMonitor
    from app.config import SNMPConfig

    try:
        snmp_config = SNMPConfig(**request.config)
    except Exception as e:
        return {
            "success": False,
            "message": f"Invalid SNMP configuration: {str(e)}",
            "speeds": {},
        }

    try:
        monitor = SNMPMonitor(snmp_config)

        speeds = await monitor.poll_interface_speeds(
            interface_indices=request.interface_indices,
        )
        await monitor.close()

        # Convert keys back to strings for JSON
        speeds_json = {str(k): v for k, v in speeds.items()}

        return {
            "success": True,
            "speeds": speeds_json,
        }

    except Exception as e:
        from loguru import logger

        logger.error(f"SNMP speed polling failed: {e}")
        return {
            "success": False,
            "message": f"Speed polling failed: {str(e)}",
        }


# Download Clients Management Endpoints

class DownloadClientResponse(BaseModel):
    """Response for download clients."""
    clients: List[Dict[str, Any]]
    connection_results: Optional[Dict[str, bool]] = None


class DownloadClientsUpdateRequest(BaseModel):
    """Request to update download clients."""
    clients: List[Dict[str, Any]]


@router.get("/download-clients", response_model=DownloadClientResponse)
async def get_download_clients(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    """Get all download clients configuration."""
    config: SpeedarrConfig = request.app.state.config

    clients = config.get_all_download_clients()

    # Convert to dict and mask sensitive values
    clients_data = []
    for client in clients:
        client_dict = client.model_dump()
        # Mask sensitive fields
        if client_dict.get("password"):
            client_dict["password"] = "***REDACTED***"
        if client_dict.get("api_key"):
            client_dict["api_key"] = "***REDACTED***"
        clients_data.append(client_dict)

    return DownloadClientResponse(clients=clients_data)


@router.put("/download-clients", response_model=DownloadClientResponse)
async def update_download_clients(
    update_request: DownloadClientsUpdateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Update all download clients configuration.

    This replaces the entire download_clients list and clears legacy configs.
    """
    if not hasattr(request.app.state, "config_manager"):
        request.app.state.config_manager = ConfigManager(request.app)

    config_manager: ConfigManager = request.app.state.config_manager
    config: SpeedarrConfig = request.app.state.config

    # Handle setup mode where config may be None
    is_setup_mode = config is None

    try:
        # Get existing clients to preserve passwords/api_keys if masked
        existing_clients = {} if is_setup_mode else {c.id: c for c in config.get_all_download_clients()}

        # Process each client
        processed_clients = []
        for client_data in update_request.clients:
            client_id = client_data.get("id")
            existing = existing_clients.get(client_id) if client_id else None

            # Preserve password if masked (but allow empty string to clear it)
            if client_data.get("password") == "***REDACTED***":
                if existing and existing.password:
                    client_data["password"] = existing.password
                else:
                    client_data["password"] = None

            # Preserve api_key if masked (but allow empty string to clear it)
            if client_data.get("api_key") == "***REDACTED***":
                if existing and existing.api_key:
                    client_data["api_key"] = existing.api_key
                else:
                    client_data["api_key"] = None

            # Validate and create client config
            try:
                client_config = DownloadClientConfig(**client_data)
                processed_clients.append(client_config)
            except Exception as e:
                raise ValueError(f"Invalid client configuration for {client_data.get('name', 'unknown')}: {e}")

        # Check if enabled client types changed - if so, reset percentage splits
        old_enabled_types = set() if is_setup_mode else {c.type for c in config.get_enabled_download_clients()}
        new_enabled_types = {c.type for c in processed_clients if c.enabled}

        # Update configuration
        # In setup mode, load the current config from database (it was initialized earlier)
        if is_setup_mode:
            config = await config_manager.load_config_from_db(db)
            if not config:
                raise ValueError("Configuration not initialized. Call /initialize-config first.")

        # Clear legacy configs and use only download_clients
        new_config_data = config.model_dump()
        new_config_data["download_clients"] = [c.model_dump() for c in processed_clients]
        # Remove legacy configs to avoid duplication (don't set to None, remove entirely)
        new_config_data.pop("qbittorrent", None)
        new_config_data.pop("sabnzbd", None)

        # Reset bandwidth percentages if enabled client types changed
        if old_enabled_types != new_enabled_types:
            logger.info(f"Enabled client types changed from {old_enabled_types} to {new_enabled_types}, resetting bandwidth splits")
            new_config_data["bandwidth"]["download"]["client_percents"] = {}
            new_config_data["bandwidth"]["upload"]["upload_client_percents"] = {}

        # Update via config manager
        updated_config = await config_manager.update_full_config(
            config_data=new_config_data,
            db=db,
            user_id=current_user.id,
        )

        # Test connections after reload (skip during setup mode)
        connection_results = {}
        if hasattr(request.app.state, "controller_manager") and request.app.state.controller_manager is not None:
            connection_results = await request.app.state.controller_manager.test_connections()

        # Return updated clients (masked) with connection results
        clients_data = []
        for client in updated_config.get_all_download_clients():
            client_dict = client.model_dump()
            if client_dict.get("password"):
                client_dict["password"] = "***REDACTED***"
            if client_dict.get("api_key"):
                client_dict["api_key"] = "***REDACTED***"
            clients_data.append(client_dict)

        return DownloadClientResponse(clients=clients_data, connection_results=connection_results)

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to update download clients: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update download clients: {str(e)}",
        )


def _find_existing_client(config: SpeedarrConfig, client_id: Optional[str], client_type: str) -> Optional[DownloadClientConfig]:
    """Find an existing download client by ID or type."""
    all_clients = config.get_all_download_clients()

    # First try to find by ID
    if client_id:
        for client in all_clients:
            if client.id == client_id:
                return client

    # Fall back to finding by type
    for client in all_clients:
        if client.type == client_type:
            return client

    return None


def _mask_sensitive_values(config: Dict[str, Any]) -> Dict[str, Any]:
    """Mask sensitive configuration values in API responses."""
    masked = config.copy()

    sensitive_keys = ["password", "api_key", "secret", "webhook_url", "token"]

    for key, value in masked.items():
        if isinstance(value, dict):
            masked[key] = _mask_sensitive_values(value)
        elif isinstance(value, str) and any(
            sensitive in key.lower() for sensitive in sensitive_keys
        ):
            masked[key] = "***REDACTED***"

    return masked
