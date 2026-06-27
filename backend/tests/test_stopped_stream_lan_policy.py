"""Stopped-stream LAN hold must follow the per-stream policy, not the legacy global flag.

Regression: _handle_stopped_stream read self.config.plex.include_lan_streams, so a
stopped Emby stream or a second Plex instance's stream got the wrong LAN policy.
"""
import pytest
from unittest.mock import AsyncMock

from app.services.polling_monitor import PollingMonitor
from app.services.decision_engine import DecisionEngine
from app.config import (
    SpeedarrConfig,
    BandwidthConfig,
    DownloadBandwidthConfig,
    UploadBandwidthConfig,
    StreamBandwidthConfig,
)


def _make_monitor(global_lan: bool) -> PollingMonitor:
    config = SpeedarrConfig(
        bandwidth=BandwidthConfig(
            download=DownloadBandwidthConfig(total_limit=100.0, min_limit_mbps=1.0),
            upload=UploadBandwidthConfig(total_limit=50.0, min_limit_mbps=1.0),
            streams=StreamBandwidthConfig(),
        )
    )
    # Legacy global flag — must NOT govern the decision.
    config.plex.include_lan_streams = global_lan
    monitor = PollingMonitor(config, DecisionEngine(config), controller_manager=None)
    monitor.schedule_restoration = AsyncMock()
    monitor.clear_session_bandwidth = AsyncMock()
    return monitor


def _lan_stream(include_lan: bool) -> dict:
    return {
        "session_id": "plex_1:abc",
        "user_id": "u1",
        "user_name": "Alice",
        "player": "Web",
        "media_title": "Movie",
        "media_type": "movie",
        "duration_seconds": 7200,
        "progress_seconds": 60,
        "is_lan": True,
        "include_lan_streams": include_lan,
        "stream_bitrate_mbps": 10.0,
        "stream_bandwidth_mbps": 10.0,
    }


@pytest.mark.asyncio
async def test_lan_stream_skips_hold_when_per_stream_policy_excludes():
    # Global says INCLUDE, per-stream says EXCLUDE -> must skip (per-stream wins).
    monitor = _make_monitor(global_lan=True)
    await monitor._handle_stopped_stream(_lan_stream(include_lan=False))
    monitor.schedule_restoration.assert_not_called()


@pytest.mark.asyncio
async def test_lan_stream_holds_when_per_stream_policy_includes():
    # Global says EXCLUDE, per-stream says INCLUDE -> must hold (per-stream wins).
    monitor = _make_monitor(global_lan=False)
    await monitor._handle_stopped_stream(_lan_stream(include_lan=True))
    monitor.schedule_restoration.assert_called_once()
