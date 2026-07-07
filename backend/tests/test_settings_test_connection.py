"""Regression tests for the settings test-connection endpoint.

Issue #49: clicking Test Connection for Jellyfin/Emby raised
UnboundLocalError ("cannot access local variable 'MediaServerConfig'")
because the Plex branch had a redundant function-local import that made
the name local to the whole handler. These tests call the handler
directly with patched clients so no network/DB is needed.
"""
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.api import settings
from app.config import (
    SpeedarrConfig,
    BandwidthConfig,
    DownloadBandwidthConfig,
    UploadBandwidthConfig,
    StreamBandwidthConfig,
)


def _minimal_config():
    """Build a minimal valid SpeedarrConfig (no media servers, no clients)."""
    return SpeedarrConfig(
        bandwidth=BandwidthConfig(
            download=DownloadBandwidthConfig(total_limit=100.0),
            upload=UploadBandwidthConfig(total_limit=50.0),
            streams=StreamBandwidthConfig(),
        )
    )


class _FakeMediaServer:
    """Stand-in client: connects successfully, closes cleanly."""

    async def test_connection(self):
        return True

    async def close(self):
        return None


def _request_with_config(config):
    """Minimal stand-in for FastAPI Request exposing app.state.config."""
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(config=config)))


@pytest.mark.parametrize("service", ["emby", "jellyfin"])
async def test_media_server_test_connection_succeeds(service):
    request = _request_with_config(_minimal_config())
    test_request = settings.TestConnectionRequest(
        config={"url": "http://media:8096", "api_key": "secret"},
        use_existing=False,
    )
    with patch(
        "app.clients.media_server_factory.create_media_server",
        return_value=_FakeMediaServer(),
    ):
        resp = await settings.test_connection(service, test_request, request, current_user=None)

    assert "cannot access local variable" not in resp.message
    assert resp.success is True


async def test_plex_test_connection_still_succeeds():
    """Guard: removing the local import must not regress the Plex path."""
    request = _request_with_config(_minimal_config())
    test_request = settings.TestConnectionRequest(
        config={"url": "http://plex:32400", "token": "tok"},
        use_existing=False,
    )
    with patch("app.clients.plex.PlexClient", return_value=_FakeMediaServer()):
        resp = await settings.test_connection("plex", test_request, request, current_user=None)

    assert "cannot access local variable" not in resp.message
    assert resp.success is True
