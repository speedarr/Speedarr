"""UnraidConfig schema (issue #30)."""
import pytest
from pydantic import ValidationError

from app.config import UnraidConfig, SpeedarrConfig
from tests.conftest import make_config


def test_defaults_are_disabled_and_safe():
    c = UnraidConfig()
    assert c.enabled is False
    assert c.verify_ssl is False
    assert c.poll_interval_seconds == 30
    assert c.throttle_on_parity_check is True
    assert c.throttle_on_mover is True
    assert c.throttle_on_array_degraded is False
    assert c.download_limit_mbps == 0
    assert c.upload_limit_mbps == 0


def test_negative_limits_rejected():
    with pytest.raises(ValidationError):
        UnraidConfig(download_limit_mbps=-1)
    with pytest.raises(ValidationError):
        UnraidConfig(upload_limit_mbps=-5)


def test_poll_interval_bounds():
    with pytest.raises(ValidationError):
        UnraidConfig(poll_interval_seconds=5)   # below floor of 10
    with pytest.raises(ValidationError):
        UnraidConfig(poll_interval_seconds=999)  # above ceiling of 300
    assert UnraidConfig(poll_interval_seconds=60).poll_interval_seconds == 60


def test_speedarr_config_has_unraid_default():
    cfg = make_config()
    assert isinstance(cfg.unraid, UnraidConfig)
    assert cfg.unraid.enabled is False
