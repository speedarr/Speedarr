"""
Configuration management for Speedarr.
"""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings
import json
from pathlib import Path
from cryptography.fernet import Fernet
import os
import logging

logger = logging.getLogger(__name__)


class PlexConfig(BaseModel):
    """Plex Media Server configuration."""
    url: str = ""  # http://192.168.1.100:32400
    token: str = ""  # X-Plex-Token
    include_lan_streams: bool = Field(
        default=False,
        description="Include LAN streams in bandwidth calculations (WAN-only by default)"
    )


class QBittorrentConfig(BaseModel):
    """qBittorrent service configuration."""
    url: str
    username: str
    password: str
    enabled: bool = True


class SABnzbdConfig(BaseModel):
    """SABnzbd service configuration."""
    url: str
    api_key: str
    enabled: bool = True
    max_speed_mbps: float = Field(
        900.0,
        description="Maximum download speed configured in SABnzbd (Mbps). Must match SABnzbd's Speed Limit setting."
    )


# New unified download client configuration
class DownloadClientConfig(BaseModel):
    """Unified download client configuration supporting multiple client types."""
    id: str = Field(..., description="Unique identifier for this client instance")
    type: str = Field(..., description="Client type: qbittorrent, sabnzbd, nzbget, transmission, deluge")
    name: str = Field(..., description="Display name for this client")
    enabled: bool = True
    url: str
    # Auth fields (used by different clients)
    username: Optional[str] = None
    password: Optional[str] = None
    api_key: Optional[str] = None
    # Client-specific settings
    max_speed_mbps: Optional[float] = Field(None, description="Max speed for clients that need it (SABnzbd, NZBGet)")
    # Bandwidth allocation
    color: str = Field("#3b82f6", description="Color for charts and UI")
    supports_upload: bool = Field(False, description="Whether this client has upload (torrents do, usenet doesn't)")


class SNMPConfig(BaseModel):
    """SNMP monitoring configuration (v2c only)."""
    enabled: bool = False
    host: str = ""
    port: int = 161
    version: str = "v2c"  # Only v2c is supported
    community: str = "public"  # SNMP v2c community string
    interface: str = ""  # Interface name or SNMP index


class TimeBasedScheduleConfig(BaseModel):
    """Time-based bandwidth schedule configuration."""
    enabled: bool = Field(False, description="Whether this time-based schedule is active")
    start_time: str = Field("22:00", description="Start time in 24-hour format (HH:MM)")
    end_time: str = Field("06:00", description="End time in 24-hour format (HH:MM)")
    total_limit: float = Field(0, description="Alternate bandwidth limit during scheduled time (Mbps)")
    client_percents: Dict[str, int] = Field(
        default_factory=dict,
        description="Alternate client percentages during scheduled time"
    )


class DownloadBandwidthConfig(BaseModel):
    """Download bandwidth configuration."""
    total_limit: float = Field(..., description="Total download bandwidth in Mbps")

    # Client percentages when multiple clients are downloading (maps client_type -> percent)
    # When no clients are downloading: equal split
    # When one client is downloading: 95% to active, 5% safety net
    # When multiple clients are downloading: use these percentages
    client_percents: Dict[str, int] = Field(
        default_factory=dict,
        description="Client percentages when multiple clients are downloading"
    )

    # Single active allocation (inactive client gets safety net %)
    inactive_safety_net_percent: int = Field(
        5,
        description="Minimum % for inactive client (allows activity detection)"
    )

    # Time-based schedule for alternate download settings
    scheduled: TimeBasedScheduleConfig = Field(
        default_factory=TimeBasedScheduleConfig,
        description="Time-based alternate download settings"
    )


class UploadBandwidthConfig(BaseModel):
    """Upload bandwidth configuration."""
    total_limit: float = Field(..., description="Total upload bandwidth in Mbps")
    # Client percentages for upload bandwidth splitting (maps client_type -> percent)
    upload_client_percents: Dict[str, int] = Field(
        default_factory=dict,
        description="Upload client percentages for bandwidth splitting"
    )

    # Time-based schedule for alternate upload settings
    scheduled: TimeBasedScheduleConfig = Field(
        default_factory=TimeBasedScheduleConfig,
        description="Time-based alternate upload settings"
    )


class StreamBandwidthConfig(BaseModel):
    """Stream bandwidth calculation configuration."""
    bandwidth_calculation: str = Field("auto", description="auto or manual")
    manual_per_stream: float = Field(15, description="Bandwidth per stream if manual")
    overhead_percent: int = Field(100, description="Protocol overhead percentage")


class BandwidthConfig(BaseModel):
    """Bandwidth management configuration."""
    download: DownloadBandwidthConfig
    upload: UploadBandwidthConfig
    streams: StreamBandwidthConfig = Field(default_factory=StreamBandwidthConfig)


class RestorationDelaysConfig(BaseModel):
    """Restoration delay configuration."""
    episode_end: int = Field(600, description="Delay after episode ends (seconds) - allows time for next episode")
    movie_end: int = Field(1800, description="Delay after movie ends (seconds) - allows time for credits/next movie")


class RestorationConfig(BaseModel):
    """Restoration logic configuration."""
    delays: RestorationDelaysConfig = Field(default_factory=RestorationDelaysConfig)


class DiscordNotificationConfig(BaseModel):
    """Discord notification configuration."""
    enabled: bool = False
    webhook_url: Optional[str] = None
    events: List[str] = Field(default_factory=lambda: [
        "stream_started", "stream_ended", "stream_count_exceeded",
        "stream_bitrate_exceeded", "service_unreachable"
    ])
    rate_limit: int = Field(60, description="Seconds between same event type")


class PushoverNotificationConfig(BaseModel):
    """Pushover notification configuration."""
    enabled: bool = False
    user_key: Optional[str] = None
    api_token: Optional[str] = None
    priority: int = Field(0, ge=-2, le=2, description="Message priority (-2 to 2)")
    events: List[str] = Field(default_factory=lambda: [
        "stream_started", "stream_ended", "stream_count_exceeded",
        "stream_bitrate_exceeded", "service_unreachable"
    ])


class TelegramNotificationConfig(BaseModel):
    """Telegram notification configuration."""
    enabled: bool = False
    bot_token: Optional[str] = None
    chat_id: Optional[str] = None
    events: List[str] = Field(default_factory=lambda: [
        "stream_started", "stream_ended", "stream_count_exceeded",
        "stream_bitrate_exceeded", "service_unreachable"
    ])


class GotifyNotificationConfig(BaseModel):
    """Gotify notification configuration."""
    enabled: bool = False
    server_url: Optional[str] = None
    app_token: Optional[str] = None
    priority: int = Field(5, ge=0, le=10, description="Message priority (0-10)")
    events: List[str] = Field(default_factory=lambda: [
        "stream_started", "stream_ended", "stream_count_exceeded",
        "stream_bitrate_exceeded", "service_unreachable"
    ])


class NtfyNotificationConfig(BaseModel):
    """ntfy notification configuration."""
    enabled: bool = False
    server_url: str = Field("https://ntfy.sh", description="ntfy server URL")
    topic: Optional[str] = None
    priority: int = Field(3, ge=1, le=5, description="Message priority (1-5)")
    events: List[str] = Field(default_factory=lambda: [
        "stream_started", "stream_ended", "stream_count_exceeded",
        "stream_bitrate_exceeded", "service_unreachable"
    ])


class WebhookNotificationConfig(BaseModel):
    """Generic webhook notification configuration."""
    name: str
    url: str
    method: str = "POST"
    headers: Dict[str, str] = Field(default_factory=dict)
    events: List[str] = Field(default_factory=list)
    format: str = "json"


class NotificationsConfig(BaseModel):
    """Notifications configuration."""
    discord: DiscordNotificationConfig = Field(default_factory=DiscordNotificationConfig)
    pushover: PushoverNotificationConfig = Field(default_factory=PushoverNotificationConfig)
    telegram: TelegramNotificationConfig = Field(default_factory=TelegramNotificationConfig)
    gotify: GotifyNotificationConfig = Field(default_factory=GotifyNotificationConfig)
    ntfy: NtfyNotificationConfig = Field(default_factory=NtfyNotificationConfig)
    webhooks: List[WebhookNotificationConfig] = Field(default_factory=list)
    stream_count_threshold: Optional[int] = Field(
        None,
        description="Notify when active streams exceed this count (null to disable)"
    )
    stream_bitrate_threshold: Optional[float] = Field(
        None,
        description="Notify when total stream bitrate exceeds this value in Mbps (null to disable)"
    )


class HistoryConfig(BaseModel):
    """Historical data configuration."""
    retention_days: int = Field(3, ge=1, le=90, description="Data retention period in days (1-90, default: 3)")


class FailsafeConfig(BaseModel):
    """Failsafe configuration."""
    plex_timeout: int = Field(300, description="Seconds before assuming no streams")
    shutdown_download_speed: Optional[float] = Field(10.0, description="Download speed on shutdown (Mbps), null = leave unchanged")
    shutdown_upload_speed: Optional[float] = Field(10.0, description="Upload speed on shutdown (Mbps), null = leave unchanged")


class SystemConfig(BaseModel):
    """System configuration."""
    update_frequency: int = Field(5, ge=5, description="Polling interval in seconds (minimum 5)")
    log_level: str = "INFO"
    speedarr_url: str = Field("", description="Base URL of Speedarr instance for webhooks (empty = auto-detect from browser)")


def _atomic_write_file(file_path: Path, content: bytes | str, mode: str = "text") -> bool:
    """
    Atomically write content to a file using a temporary file and rename.
    This prevents race conditions and partial writes.

    Args:
        file_path: Target file path
        content: Content to write (bytes or str)
        mode: "text" or "binary"

    Returns:
        True if successful, False otherwise
    """
    import tempfile
    temp_file = None
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        # Create temp file in same directory for atomic rename
        fd, temp_path = tempfile.mkstemp(dir=file_path.parent)
        temp_file = Path(temp_path)

        if mode == "binary":
            os.write(fd, content if isinstance(content, bytes) else content.encode())
        else:
            os.write(fd, content.encode() if isinstance(content, str) else content)
        os.close(fd)

        # Set permissions before rename
        temp_file.chmod(0o600)
        # Atomic rename
        temp_file.rename(file_path)
        return True
    except Exception as e:
        logger.warning(f"Failed to atomically write {file_path}: {e}")
        if temp_file and temp_file.exists():
            try:
                temp_file.unlink()
            except Exception:
                pass
        return False


def get_jwt_secret() -> str:
    """
    Get or create JWT secret key for authentication.

    Priority order:
    1. AUTH__SECRET_KEY environment variable
    2. Stored key in /data/.jwt_secret file
    3. Generate new key and save to file (atomic write)
    """
    import secrets

    # Check environment variable first
    key_env = os.getenv("AUTH__SECRET_KEY")
    if key_env and key_env != "change-me-in-production":
        # Validate key length
        if len(key_env) < 32:
            logger.warning(f"JWT secret from environment is weak ({len(key_env)} chars)")
        return key_env

    # Try to load from persistent file
    key_file = Path("/data/.jwt_secret")
    if key_file.exists():
        try:
            stored_key = key_file.read_text().strip()
            if stored_key and len(stored_key) >= 32:
                return stored_key
            elif stored_key:
                logger.warning("Stored JWT secret is too short, regenerating")
        except Exception as e:
            logger.warning(f"Failed to read JWT secret file: {e}")

    # Generate new secure key (64 hex characters = 256 bits)
    new_key = secrets.token_hex(32)
    if _atomic_write_file(key_file, new_key):
        logger.info("Generated new JWT secret and saved to /data/.jwt_secret")
    else:
        logger.warning("Could not persist JWT secret - will regenerate on restart")

    return new_key


class AuthConfig(BaseModel):
    """Authentication configuration."""
    session_timeout: int = Field(86400, description="Session timeout in seconds (24 hours)")
    secret_key: str = Field(default_factory=get_jwt_secret, description="JWT secret key (auto-generated if not set)")
    algorithm: str = "HS256"


class Settings(BaseSettings):
    """Application settings loaded from environment and config file."""

    # Application
    app_name: str = "Speedarr"
    app_version: str = Field(default_factory=lambda: __import__('app').__version__)
    debug: bool = False

    # Server
    host: str = "0.0.0.0"
    port: int = 9494

    # Database (SQLite for single-container deployment)
    database_url: str = Field(
        "sqlite+aiosqlite:////data/speedarr.db",
        description="Database connection URL (SQLite embedded)"
    )

    # Auth
    auth: AuthConfig = Field(default_factory=AuthConfig)

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        env_nested_delimiter = "__"


class SpeedarrConfig(BaseModel):
    """Main Speedarr configuration stored in database."""
    system: SystemConfig = Field(default_factory=SystemConfig)
    plex: PlexConfig = Field(default_factory=PlexConfig)
    # Legacy single-client configs (for backward compatibility)
    qbittorrent: Optional[QBittorrentConfig] = None
    sabnzbd: Optional[SABnzbdConfig] = None
    # New multi-client config
    download_clients: List[DownloadClientConfig] = Field(default_factory=list)
    snmp: SNMPConfig = Field(default_factory=SNMPConfig)
    bandwidth: BandwidthConfig
    restoration: RestorationConfig = Field(default_factory=RestorationConfig)
    notifications: NotificationsConfig = Field(default_factory=NotificationsConfig)
    history: HistoryConfig = Field(default_factory=HistoryConfig)
    failsafe: FailsafeConfig = Field(default_factory=FailsafeConfig)

    def get_all_download_clients(self) -> List[DownloadClientConfig]:
        """
        Get all download clients, merging legacy configs into the new format.
        This provides backward compatibility while supporting the new multi-client system.
        """
        clients = list(self.download_clients)
        existing_ids = {c.id for c in clients}

        # Add legacy qbittorrent if not already in download_clients
        if self.qbittorrent and "qbittorrent" not in existing_ids:
            clients.append(DownloadClientConfig(
                id="qbittorrent",
                type="qbittorrent",
                name="qBittorrent",
                enabled=self.qbittorrent.enabled,
                url=self.qbittorrent.url,
                username=self.qbittorrent.username,
                password=self.qbittorrent.password,
                color="#3b82f6",
                supports_upload=True
            ))

        # Add legacy sabnzbd if not already in download_clients
        if self.sabnzbd and "sabnzbd" not in existing_ids:
            clients.append(DownloadClientConfig(
                id="sabnzbd",
                type="sabnzbd",
                name="SABnzbd",
                enabled=self.sabnzbd.enabled,
                url=self.sabnzbd.url,
                api_key=self.sabnzbd.api_key,
                max_speed_mbps=self.sabnzbd.max_speed_mbps,
                color="#facc15",
                supports_upload=False
            ))

        return clients

    def get_enabled_download_clients(self) -> List[DownloadClientConfig]:
        """Get only enabled download clients."""
        return [c for c in self.get_all_download_clients() if c.enabled]

    def get_upload_clients(self) -> List[DownloadClientConfig]:
        """Get enabled clients that support upload (torrent clients)."""
        return [c for c in self.get_enabled_download_clients() if c.supports_upload]


# Global settings instance
settings = Settings()


# Encryption for sensitive configuration values
def _is_valid_fernet_key(key: bytes) -> bool:
    """Validate that a key is a valid Fernet key (32 url-safe base64-encoded bytes)."""
    try:
        # Fernet keys must be 32 url-safe base64-encoded bytes
        import base64
        decoded = base64.urlsafe_b64decode(key)
        return len(decoded) == 32
    except Exception:
        return False


def get_encryption_key() -> bytes:
    """
    Get or create encryption key for sensitive config values.

    Priority order:
    1. CONFIG_ENCRYPTION_KEY environment variable (validated)
    2. Stored key in /data/.encryption_key file (validated)
    3. Generate new key and save to file (atomic write)
    """
    # Check environment variable first
    key_env = os.getenv("CONFIG_ENCRYPTION_KEY")
    if key_env:
        key_bytes = key_env.encode()
        if _is_valid_fernet_key(key_bytes):
            return key_bytes
        else:
            logger.warning("CONFIG_ENCRYPTION_KEY from environment is invalid, trying file")

    # Try to load from persistent file
    key_file = Path("/data/.encryption_key")
    if key_file.exists():
        try:
            stored_key = key_file.read_bytes()
            if _is_valid_fernet_key(stored_key):
                return stored_key
            else:
                logger.warning("Stored encryption key is invalid, regenerating")
        except Exception as e:
            logger.warning(f"Failed to read encryption key file: {e}")

    # Generate new key and save it atomically
    new_key = Fernet.generate_key()
    if _atomic_write_file(key_file, new_key, mode="binary"):
        logger.info("Generated new encryption key and saved to /data/.encryption_key")
    else:
        logger.warning("Could not persist encryption key - will regenerate on restart")

    return new_key


_fernet = Fernet(get_encryption_key())


def encrypt_value(value: str) -> str:
    """Encrypt a sensitive configuration value."""
    return _fernet.encrypt(value.encode()).decode()


def decrypt_value(encrypted: str) -> str:
    """Decrypt a sensitive configuration value."""
    return _fernet.decrypt(encrypted.encode()).decode()


# Database serialization helpers
def flatten_dict(d: Dict[str, Any], parent_key: str = "", sep: str = ".") -> Dict[str, Any]:
    """
    Flatten a nested dictionary into dot-notation keys.

    Example:
        {"bandwidth": {"download": {"total_limit": 900}}}
        becomes
        {"bandwidth.download.total_limit": 900}
    """
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        elif isinstance(v, list):
            # Store lists as JSON
            items.append((new_key, v))
        else:
            items.append((new_key, v))
    return dict(items)


def unflatten_dict(d: Dict[str, Any], sep: str = ".") -> Dict[str, Any]:
    """
    Unflatten a dictionary with dot-notation keys into nested structure.

    Example:
        {"bandwidth.download.total_limit": 900}
        becomes
        {"bandwidth": {"download": {"total_limit": 900}}}
    """
    result = {}
    for key, value in d.items():
        parts = key.split(sep)
        current = result
        for part in parts[:-1]:
            if part not in current:
                current[part] = {}
            current = current[part]
        current[parts[-1]] = value
    return result


def get_value_type(value: Any) -> str:
    """Determine the type of a configuration value."""
    if isinstance(value, bool):
        return "boolean"
    elif isinstance(value, int):
        return "integer"
    elif isinstance(value, float):
        return "float"
    elif isinstance(value, (list, dict)):
        return "json"
    else:
        return "string"


def serialize_value(value: Any, value_type: str) -> str:
    """Serialize a value for database storage."""
    if value_type == "json":
        return json.dumps(value)
    elif value_type == "boolean":
        return str(value).lower()
    else:
        return str(value)


def deserialize_value(value_str: str, value_type: str) -> Any:
    """Deserialize a value from database storage."""
    if value_type == "json":
        return json.loads(value_str)
    elif value_type == "boolean":
        return value_str.lower() in ("true", "1", "yes")
    elif value_type == "integer":
        try:
            return int(value_str)
        except (ValueError, OverflowError):
            # Handle corrupted values (e.g., scientific notation floats stored as integers)
            try:
                float_val = float(value_str)
                if abs(float_val) > 2**31:
                    # Value is corrupted/unreasonable, return default
                    return 5  # Safe default for polling intervals
                return int(float_val)
            except (ValueError, OverflowError):
                return 5  # Safe default
    elif value_type == "float":
        try:
            val = float(value_str)
            # Sanity check for unreasonable values
            if abs(val) > 1e15:
                return 0.0  # Safe default
            return val
        except (ValueError, OverflowError):
            return 0.0
    else:
        return value_str


def is_sensitive_key(key: str) -> bool:
    """Check if a configuration key contains sensitive data."""
    sensitive_keywords = ["password", "api_key", "secret", "webhook_url", "token"]
    return any(keyword in key.lower() for keyword in sensitive_keywords)
