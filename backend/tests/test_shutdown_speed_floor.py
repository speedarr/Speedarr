"""Failsafe shutdown speed floor + validation (issue #48).

The failsafe shutdown path must never emit a per-client limit of 0, which every
download client interprets as "unlimited" -- the opposite of throttling.
Mirrors the live-throttle floor introduced in #43.
"""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app.config import FailsafeConfig
from app.services.controller_manager import ControllerManager
from app.services.decision_engine import HARD_MIN_MBPS
from tests.conftest import make_config


def _manager_with(client_configs):
    """Build a ControllerManager with no real clients, then inject client configs."""
    cm = ControllerManager(make_config())
    cm.client_configs = client_configs
    return cm


# --- _split_shutdown_speed flooring ---

def test_split_zero_total_floored_to_hard_min():
    cm = _manager_with({
        "qb": SimpleNamespace(type="qbittorrent", supports_upload=True),
        "sab": SimpleNamespace(type="sabnzbd", supports_upload=False),
    })
    result = cm._split_shutdown_speed(0.0, ["qb", "sab"], {})
    assert result["qb"] >= HARD_MIN_MBPS
    assert result["sab"] >= HARD_MIN_MBPS


def test_split_zero_percent_share_floored():
    cm = _manager_with({
        "qb": SimpleNamespace(type="qbittorrent", supports_upload=True),
        "de": SimpleNamespace(type="deluge", supports_upload=True),
    })
    # deluge configured at 0% -> would otherwise receive 0 of the 50 Mbps total
    result = cm._split_shutdown_speed(50.0, ["qb", "de"], {"qb": 100, "de": 0})
    assert result["de"] >= HARD_MIN_MBPS
    assert result["qb"] > result["de"]  # positive-share client still gets the bulk


def test_split_two_same_type_clients_by_id():
    cm = _manager_with({
        "qbittorrent_1": SimpleNamespace(type="qbittorrent", supports_upload=True),
        "qbittorrent_2": SimpleNamespace(type="qbittorrent", supports_upload=True),
    })
    result = cm._split_shutdown_speed(
        100.0, ["qbittorrent_1", "qbittorrent_2"], {"qbittorrent_1": 75, "qbittorrent_2": 25}
    )
    assert result["qbittorrent_1"] > result["qbittorrent_2"]
    assert result["qbittorrent_1"] == pytest.approx(75.0, abs=0.5)
    assert result["qbittorrent_2"] == pytest.approx(25.0, abs=0.5)


def test_split_positive_total_unchanged_above_floor():
    cm = _manager_with({
        "qb": SimpleNamespace(type="qbittorrent", supports_upload=True),
        "de": SimpleNamespace(type="deluge", supports_upload=True),
    })
    result = cm._split_shutdown_speed(10.0, ["qb", "de"], {})
    assert result == {"qb": 5.0, "de": 5.0}


# --- apply_shutdown_speeds never emits 0 to a client ---

def test_apply_shutdown_speeds_never_sends_zero():
    cm = _manager_with({
        "qb": SimpleNamespace(type="qbittorrent", supports_upload=True),
    })
    client = AsyncMock()
    cm.clients = {"qb": client}

    failsafe = FailsafeConfig(shutdown_download_speed=0.0, shutdown_upload_speed=0.0)
    asyncio.run(cm.apply_shutdown_speeds(failsafe))

    assert client.set_speed_limits.await_count == 1
    _, kwargs = client.set_speed_limits.await_args
    assert kwargs["download_limit"] >= HARD_MIN_MBPS
    assert kwargs["upload_limit"] >= HARD_MIN_MBPS


# --- FailsafeConfig validation ---

def test_negative_shutdown_speed_rejected():
    with pytest.raises(ValidationError):
        FailsafeConfig(shutdown_download_speed=-1)
    with pytest.raises(ValidationError):
        FailsafeConfig(shutdown_upload_speed=-1)


def test_zero_shutdown_speed_allowed():
    cfg = FailsafeConfig(shutdown_download_speed=0, shutdown_upload_speed=0)
    assert cfg.shutdown_download_speed == 0
    assert cfg.shutdown_upload_speed == 0
