"""POST /api/settings/test/ntfy resolves a masked topic from the saved config and pins the server (audit T1-3).

Once the topic is masked in responses, the UI posts the placeholder back; the endpoint must use
the saved topic AND the saved server, so a caller cannot make Speedarr post the stored topic to a
host they name (the T1-2 shape). Pattern: test_settings_test_connection.py.
"""
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.api import settings
from app.config import (
    SpeedarrConfig, BandwidthConfig, DownloadBandwidthConfig, UploadBandwidthConfig,
    StreamBandwidthConfig, NotificationsConfig, NtfyNotificationConfig, REDACTED,
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
        _FakeSession.posted.append(url)
        return _FakeResponse()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def _config(topic="AUDITMARK-topic", server="https://ntfy.saved.example"):
    return SpeedarrConfig(
        bandwidth=BandwidthConfig(
            download=DownloadBandwidthConfig(total_limit=100.0),
            upload=UploadBandwidthConfig(total_limit=50.0),
            streams=StreamBandwidthConfig(),
        ),
        notifications=NotificationsConfig(ntfy=NtfyNotificationConfig(enabled=True, topic=topic, server_url=server)),
    )


def _request(config):
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(config=config)))


@pytest.fixture(autouse=True)
def _reset_posts():
    _FakeSession.posted.clear()


async def _call(config, body, use_existing=False):
    req = settings.TestConnectionRequest(config=body, use_existing=use_existing)
    with patch("aiohttp.ClientSession", _FakeSession):
        return await settings.test_connection("ntfy", req, _request(config), current_user=None)


async def test_masked_topic_uses_saved_topic_and_saved_server():
    resp = await _call(_config(), {"server_url": "https://attacker.example", "topic": REDACTED})
    assert resp.success is True
    assert _FakeSession.posted == ["https://ntfy.saved.example/AUDITMARK-topic"]


async def test_use_existing_flag_also_pins_the_server():
    await _call(_config(), {"server_url": "https://attacker.example", "topic": "ignored"}, use_existing=True)
    assert _FakeSession.posted == ["https://ntfy.saved.example/AUDITMARK-topic"]


async def test_plain_topic_posts_where_the_caller_says():
    await _call(_config(), {"server_url": "https://ntfy.example", "topic": "mine"})
    assert _FakeSession.posted == ["https://ntfy.example/mine"]


async def test_no_saved_topic_is_a_failure_not_a_post():
    resp = await _call(_config(topic=None), {"topic": REDACTED})
    assert resp.success is False
    assert "No saved ntfy topic" in resp.message
    assert _FakeSession.posted == []


async def test_setup_mode_without_config_is_a_failure():
    resp = await _call(None, {"topic": REDACTED})
    assert resp.success is False
    assert _FakeSession.posted == []
