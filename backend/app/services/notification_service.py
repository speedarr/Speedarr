"""
Notification service for Discord and webhook notifications.
"""
import asyncio
import aiohttp
from typing import Dict, Any, Optional, List, Callable, Awaitable
from datetime import datetime, timedelta, timezone
from loguru import logger
from app.config import SpeedarrConfig

# Retry configuration
MAX_RETRIES = 3
INITIAL_BACKOFF_SECONDS = 1.0
BACKOFF_MULTIPLIER = 2.0


class NotificationService:
    """
    Handles sending notifications to Discord and custom webhooks.
    """

    def __init__(self, config: SpeedarrConfig):
        self.config = config
        self._session: Optional[aiohttp.ClientSession] = None
        self._last_notified_stream_count: Optional[int] = None
        self._last_notified_bitrate: Optional[float] = None

    def initialize_state(self, stream_count: int, total_bitrate: float):
        """
        Initialize notification state on startup.
        Called on first poll to log current state.

        Note: We do NOT suppress threshold notifications here - users expect to be notified
        when thresholds are exceeded, even if they were exceeded on startup. The _first_poll
        flag in polling_monitor handles suppressing stream_started notifications.
        """
        # Only log for debugging - don't set any state that would suppress threshold notifications
        logger.info(f"First poll state: {stream_count} streams, {total_bitrate:.1f} Mbps total bitrate")

    @property
    def session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10)
            )
        return self._session

    async def close(self):
        """Close the HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()

    async def _request_with_retry(
        self,
        method: str,
        url: str,
        service_name: str,
        json: Optional[Dict] = None,
        data: Optional[Any] = None,
        headers: Optional[Dict[str, str]] = None,
        expected_statuses: Optional[List[int]] = None
    ) -> bool:
        """
        Make HTTP request with exponential backoff retry.

        Args:
            method: HTTP method (GET, POST, etc.)
            url: Request URL
            service_name: Name of service for logging
            json: JSON payload
            data: Form data payload
            headers: Request headers
            expected_statuses: List of success status codes (default: 200-299)

        Returns:
            True if request succeeded, False otherwise
        """
        if expected_statuses is None:
            expected_statuses = list(range(200, 300))

        backoff = INITIAL_BACKOFF_SECONDS
        last_error = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                async with self.session.request(
                    method,
                    url,
                    json=json,
                    data=data,
                    headers=headers
                ) as response:
                    if response.status in expected_statuses:
                        logger.debug(f"{service_name} notification sent successfully")
                        return True
                    else:
                        response_text = await response.text()
                        last_error = f"HTTP {response.status}: {response_text[:200]}"
                        logger.warning(
                            f"{service_name} notification failed (attempt {attempt}/{MAX_RETRIES}): {last_error}"
                        )
            except asyncio.CancelledError:
                raise  # Don't retry on cancellation
            except Exception as e:
                last_error = str(e)
                logger.warning(
                    f"{service_name} notification failed (attempt {attempt}/{MAX_RETRIES}): {last_error}"
                )

            # Don't sleep after last attempt
            if attempt < MAX_RETRIES:
                logger.debug(f"Retrying {service_name} notification in {backoff}s...")
                await asyncio.sleep(backoff)
                backoff *= BACKOFF_MULTIPLIER

        logger.error(f"Failed to send {service_name} notification after {MAX_RETRIES} attempts: {last_error}")
        return False

    async def notify(self, event_type: str, message: str, data: Optional[Dict[str, Any]] = None):
        """
        Send notification to all configured channels.

        Args:
            event_type: Type of event (stream_started, speeds_restored, etc.)
            message: Human-readable message
            data: Additional event data
        """
        logger.info(f"Notification requested: event_type={event_type}, message={message[:50]}...")

        # Send to Discord if configured
        if self.config.notifications.discord.enabled:
            if event_type in self.config.notifications.discord.events:
                logger.info(f"Sending Discord notification: {event_type}")
                await self._send_discord(event_type, message, data)
            else:
                logger.debug(f"Discord: event '{event_type}' not in enabled events {self.config.notifications.discord.events}")
        else:
            logger.debug(f"Discord: service disabled")

        # Send to Pushover if configured
        if self.config.notifications.pushover.enabled:
            if event_type in self.config.notifications.pushover.events:
                logger.info(f"Sending Pushover notification: {event_type}")
                await self._send_pushover(event_type, message, data)
            else:
                logger.debug(f"Pushover: event '{event_type}' not in enabled events {self.config.notifications.pushover.events}")
        else:
            logger.debug(f"Pushover: service disabled")

        # Send to Telegram if configured
        if self.config.notifications.telegram.enabled:
            if event_type in self.config.notifications.telegram.events:
                logger.info(f"Sending Telegram notification: {event_type}")
                await self._send_telegram(event_type, message, data)
            else:
                logger.debug(f"Telegram: event '{event_type}' not in enabled events {self.config.notifications.telegram.events}")
        else:
            logger.debug(f"Telegram: service disabled")

        # Send to Gotify if configured
        if self.config.notifications.gotify.enabled:
            if event_type in self.config.notifications.gotify.events:
                logger.info(f"Sending Gotify notification: {event_type}")
                await self._send_gotify(event_type, message, data)
            else:
                logger.debug(f"Gotify: event '{event_type}' not in enabled events {self.config.notifications.gotify.events}")
        else:
            logger.debug(f"Gotify: service disabled")

        # Send to ntfy if configured
        if self.config.notifications.ntfy.enabled:
            if event_type in self.config.notifications.ntfy.events:
                logger.info(f"Sending ntfy notification: {event_type}")
                await self._send_ntfy(event_type, message, data)
            else:
                logger.debug(f"ntfy: event '{event_type}' not in enabled events {self.config.notifications.ntfy.events}")
        else:
            logger.debug(f"ntfy: service disabled")

        # Send to custom webhooks
        for webhook_config in self.config.notifications.webhooks:
            if event_type in webhook_config.events:
                logger.info(f"Sending webhook notification to {webhook_config.name}: {event_type}")
                await self._send_webhook(webhook_config, event_type, message, data)
            else:
                logger.debug(f"Webhook {webhook_config.name}: event '{event_type}' not in enabled events {webhook_config.events}")

    async def _send_discord(self, event_type: str, message: str, data: Optional[Dict[str, Any]]):
        """Send notification to Discord."""
        if not self.config.notifications.discord.webhook_url:
            return

        # Format message with emoji
        emoji = self._get_emoji_for_event(event_type, data)
        formatted_message = f"{emoji} {message}"

        payload = {
            "content": formatted_message,
            "username": "Speedarr"
        }

        await self._request_with_retry(
            method="POST",
            url=self.config.notifications.discord.webhook_url,
            service_name="Discord",
            json=payload,
            expected_statuses=[200, 204]  # Discord returns 204 on success
        )

    async def _send_webhook(
        self,
        webhook_config,
        event_type: str,
        message: str,
        data: Optional[Dict[str, Any]]
    ):
        """Send notification to custom webhook."""
        payload = {
            "event": event_type,
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": data or {}
        }

        await self._request_with_retry(
            method=webhook_config.method,
            url=webhook_config.url,
            service_name=f"Webhook ({webhook_config.name})",
            json=payload if webhook_config.format == "json" else None,
            data=payload if webhook_config.format != "json" else None,
            headers=webhook_config.headers
        )

    async def _send_pushover(self, event_type: str, message: str, data: Optional[Dict[str, Any]]):
        """Send notification via Pushover."""
        cfg = self.config.notifications.pushover
        if not cfg.user_key or not cfg.api_token:
            return

        emoji = self._get_emoji_for_event(event_type, data)
        title = f"{emoji} Speedarr: {event_type.replace('_', ' ').title()}"

        payload = {
            "token": cfg.api_token,
            "user": cfg.user_key,
            "title": title,
            "message": message,
            "priority": cfg.priority,
        }

        await self._request_with_retry(
            method="POST",
            url="https://api.pushover.net/1/messages.json",
            service_name="Pushover",
            data=payload
        )

    async def _send_telegram(self, event_type: str, message: str, data: Optional[Dict[str, Any]]):
        """Send notification via Telegram."""
        cfg = self.config.notifications.telegram
        if not cfg.bot_token or not cfg.chat_id:
            return

        emoji = self._get_emoji_for_event(event_type, data)
        formatted_message = f"{emoji} <b>Speedarr</b>\n{message}"

        url = f"https://api.telegram.org/bot{cfg.bot_token}/sendMessage"
        payload = {
            "chat_id": cfg.chat_id,
            "text": formatted_message,
            "parse_mode": "HTML",
        }

        await self._request_with_retry(
            method="POST",
            url=url,
            service_name="Telegram",
            json=payload
        )

    async def _send_gotify(self, event_type: str, message: str, data: Optional[Dict[str, Any]]):
        """Send notification via Gotify."""
        cfg = self.config.notifications.gotify
        if not cfg.server_url or not cfg.app_token:
            return

        emoji = self._get_emoji_for_event(event_type, data)
        title = f"{emoji} Speedarr: {event_type.replace('_', ' ').title()}"

        url = f"{cfg.server_url.rstrip('/')}/message"
        payload = {
            "title": title,
            "message": message,
            "priority": cfg.priority,
        }
        headers = {"X-Gotify-Key": cfg.app_token}

        await self._request_with_retry(
            method="POST",
            url=url,
            service_name="Gotify",
            json=payload,
            headers=headers
        )

    async def _send_ntfy(self, event_type: str, message: str, data: Optional[Dict[str, Any]]):
        """Send notification via ntfy."""
        cfg = self.config.notifications.ntfy
        if not cfg.topic:
            return

        emoji = self._get_emoji_for_event(event_type, data)
        title = f"{emoji} Speedarr: {event_type.replace('_', ' ').title()}"

        url = f"{cfg.server_url.rstrip('/')}/{cfg.topic}"
        headers = {
            "Title": title,
            "Priority": str(cfg.priority),
        }

        await self._request_with_retry(
            method="POST",
            url=url,
            service_name="ntfy",
            data=message,
            headers=headers
        )

    def _get_emoji_for_event(self, event_type: str, data: Optional[Dict[str, Any]] = None) -> str:
        """Get emoji for event type."""
        # Service recovery gets a green tick instead of red X
        if event_type == "service_unreachable" and data and data.get("status") == "recovered":
            return "✅"

        emoji_map = {
            "stream_started": "🎬",
            "stream_ended": "⏹️",
            "speeds_restored": "✅",
            "throttle_applied": "⚠️",
            "service_unreachable": "❌",
            "speeds_manually_overridden": "👤",
            "stream_count_exceeded": "📊",
            "stream_bitrate_exceeded": "📈",
        }
        return emoji_map.get(event_type, "ℹ️")

    async def check_stream_count_threshold(self, active_stream_count: int, total_bandwidth_mbps: float = 0.0):
        """
        Check if active streams exceed threshold and send notification if so.
        Only notifies if the count has changed since the last notification.

        Args:
            active_stream_count: Number of currently active streams
            total_bandwidth_mbps: Total bandwidth of all active streams in Mbps
        """
        # Get threshold from config - handle both SpeedarrConfig and NotificationsConfig
        if hasattr(self.config, 'notifications'):
            # SpeedarrConfig
            threshold = self.config.notifications.stream_count_threshold
        else:
            # NotificationsConfig directly
            threshold = getattr(self.config, 'stream_count_threshold', None)

        if threshold is None or threshold <= 0:
            return

        if active_stream_count > threshold:
            # Only notify if count has changed since last notification
            if active_stream_count == self._last_notified_stream_count:
                logger.debug(f"Skipping stream count notification (count unchanged: {active_stream_count})")
                return

            message = f"Active streams ({active_stream_count}) exceeded threshold ({threshold}) - Total: {total_bandwidth_mbps:.1f} Mbps"
            await self.notify(
                "stream_count_exceeded",
                message,
                {"active_streams": active_stream_count, "threshold": threshold, "total_bandwidth_mbps": total_bandwidth_mbps}
            )
            self._last_notified_stream_count = active_stream_count
        else:
            # Reset when back below threshold so we notify again if it exceeds
            self._last_notified_stream_count = None

    async def check_stream_bitrate_threshold(self, total_bitrate_mbps: float, active_stream_count: int = 0):
        """
        Check if total stream bitrate exceeds threshold and send notification if so.
        Only notifies if we're crossing the threshold (not for every check while above).

        Args:
            total_bitrate_mbps: Total bitrate of all active streams in Mbps
            active_stream_count: Number of currently active streams
        """
        # Get threshold from config - handle both SpeedarrConfig and NotificationsConfig
        if hasattr(self.config, 'notifications'):
            # SpeedarrConfig
            threshold = self.config.notifications.stream_bitrate_threshold
        else:
            # NotificationsConfig directly
            threshold = getattr(self.config, 'stream_bitrate_threshold', None)

        if threshold is None or threshold <= 0:
            return

        if total_bitrate_mbps > threshold:
            # Only notify if we weren't already above threshold
            if self._last_notified_bitrate is not None and self._last_notified_bitrate > threshold:
                logger.debug(f"Skipping bitrate notification (already above threshold: {total_bitrate_mbps:.1f} Mbps)")
                return

            message = f"Total stream bitrate ({total_bitrate_mbps:.1f} Mbps) exceeded threshold ({threshold:.1f} Mbps) - {active_stream_count} active stream(s)"
            await self.notify(
                "stream_bitrate_exceeded",
                message,
                {"total_bitrate_mbps": total_bitrate_mbps, "threshold": threshold, "active_streams": active_stream_count}
            )
            self._last_notified_bitrate = total_bitrate_mbps
        else:
            # Reset when back below threshold so we notify again if it exceeds
            self._last_notified_bitrate = None
