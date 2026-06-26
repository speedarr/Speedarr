"""min_limit_mbps schema behavior on bandwidth config."""
import pytest
from pydantic import ValidationError

from app.config import DownloadBandwidthConfig, UploadBandwidthConfig


def test_download_min_limit_defaults_to_one():
    cfg = DownloadBandwidthConfig(total_limit=100.0)
    assert cfg.min_limit_mbps == 1.0


def test_upload_min_limit_defaults_to_one():
    cfg = UploadBandwidthConfig(total_limit=50.0)
    assert cfg.min_limit_mbps == 1.0


def test_min_limit_zero_is_allowed():
    assert DownloadBandwidthConfig(total_limit=100.0, min_limit_mbps=0).min_limit_mbps == 0
    assert UploadBandwidthConfig(total_limit=50.0, min_limit_mbps=0).min_limit_mbps == 0


def test_negative_min_limit_rejected():
    with pytest.raises(ValidationError):
        DownloadBandwidthConfig(total_limit=100.0, min_limit_mbps=-1)
    with pytest.raises(ValidationError):
        UploadBandwidthConfig(total_limit=50.0, min_limit_mbps=-1)
