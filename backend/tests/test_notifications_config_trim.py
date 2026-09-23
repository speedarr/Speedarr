"""Notification config trimmed to what the UI can set (#106).

Discord's rate_limit was never read anywhere in the backend, and named generic
webhooks could only be configured by writing the section through the API by
hand. Both go. A stale key left in an older database is ignored on load.
"""
import app.config as config_module
from app.config import DiscordNotificationConfig, NotificationsConfig
from app.services.notification_service import NotificationService


def test_discord_has_no_rate_limit_and_ignores_a_stale_key():
    cfg = DiscordNotificationConfig(enabled=False, rate_limit=60)
    assert not hasattr(cfg, "rate_limit")


def test_notifications_have_no_generic_webhooks_and_ignore_a_stale_key():
    cfg = NotificationsConfig(webhooks=[{"name": "n", "url": "http://example", "events": []}])
    assert not hasattr(cfg, "webhooks")
    assert not hasattr(config_module, "WebhookNotificationConfig")


def test_service_has_no_generic_webhook_sender():
    assert not hasattr(NotificationService, "_send_webhook")
