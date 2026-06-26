"""Shared fixtures for Speedarr backend tests."""
import pytest

from app.config import (
    SpeedarrConfig,
    BandwidthConfig,
    DownloadBandwidthConfig,
    UploadBandwidthConfig,
    StreamBandwidthConfig,
)
from app.services.decision_engine import DecisionEngine


def make_config(download_total=100.0, upload_total=50.0, dl_min=1.0, ul_min=1.0):
    """Build a minimal valid SpeedarrConfig for decision-engine tests."""
    return SpeedarrConfig(
        bandwidth=BandwidthConfig(
            download=DownloadBandwidthConfig(total_limit=download_total, min_limit_mbps=dl_min),
            upload=UploadBandwidthConfig(total_limit=upload_total, min_limit_mbps=ul_min),
            streams=StreamBandwidthConfig(),
        )
    )


def make_stats():
    """Two idle clients: qbittorrent (upload-capable) and sabnzbd (download-only)."""
    return {
        "qbittorrent_1": {"download_speed": 0.0, "upload_speed": 0.0, "supports_upload": True},
        "sabnzbd_1": {"download_speed": 0.0, "upload_speed": 0.0, "supports_upload": False},
    }


@pytest.fixture
def make_engine():
    def _make(**kwargs):
        return DecisionEngine(make_config(**kwargs))
    return _make
