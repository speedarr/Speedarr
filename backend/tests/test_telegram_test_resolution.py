"""POST /api/settings/test/telegram never resolves a typed bot token from the saved config (final-review Fix 3).

The Telegram branch of test_connection resolves each masked field on its own (`use_existing or
field == REDACTED`). With `use_existing=False`, a freshly typed bot token must be used as-is even
when the chat id is masked and resolved from the saved config -- never the saved bot token.
Pattern: test_ntfy_test_resolution.py.
"""
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.api import settings
from app.config import (
    SpeedarrConfig, BandwidthConfig, DownloadBandwidthConfig, UploadBandwidthConfig,
    StreamBandwidthConfig, NotificationsConfig, TelegramNotificationConfig, REDACTED,
)


class _FakeResponse:
    status = 200

    async def text(self):
        return ""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _FakeSession:
    posted = []

    def post(self, url, **kwargs):
        _FakeSession.posted.append((url, kwargs.get("json")))
        return _FakeResponse()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def _config(bot_token="AUDITMARK-saved-bot-token", chat_id="AUDITMARK-saved-chat-id"):
    return SpeedarrConfig(
        bandwidth=BandwidthConfig(
            download=DownloadBandwidthConfig(total_limit=100.0),
            upload=UploadBandwidthConfig(total_limit=50.0),
            streams=StreamBandwidthConfig(),
        ),
        notifications=NotificationsConfig(
            telegram=TelegramNotificationConfig(enabled=True, bot_token=bot_token, chat_id=chat_id)
        ),
    )


def _request(config):
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(config=config)))


@pytest.fixture(autouse=True)
def _reset_posts():
    _FakeSession.posted.clear()


async def _call(config, body, use_existing=False):
    req = settings.TestConnectionRequest(config=body, use_existing=use_existing)
    with patch("aiohttp.ClientSession", _FakeSession):
        return await settings.test_connection("telegram", req, _request(config), current_user=None)


async def test_typed_bot_token_with_masked_chat_id_uses_the_typed_token_and_the_saved_chat_id():
    resp = await _call(
        _config(),
        {"bot_token": "123456:AUDITMARK-fresh-bot-token", "chat_id": REDACTED},
        use_existing=False,
    )
    assert resp.success is True
    assert len(_FakeSession.posted) == 1
    url, payload = _FakeSession.posted[0]
    assert url == "https://api.telegram.org/bot123456:AUDITMARK-fresh-bot-token/sendMessage"
    assert payload["chat_id"] == "AUDITMARK-saved-chat-id"
