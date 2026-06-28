"""Bandwidth splits are keyed by client id, so same-type clients split independently."""
import pytest

from app.services.decision_engine import DecisionEngine
from tests.conftest import make_config


def _engine_with_download_percents(percents):
    cfg = make_config(download_total=100.0)
    cfg.bandwidth.download.client_percents = percents
    return DecisionEngine(cfg)


def _engine_with_upload_percents(percents):
    cfg = make_config(upload_total=50.0)
    cfg.bandwidth.upload.upload_client_percents = percents
    return DecisionEngine(cfg)


def test_two_same_type_download_clients_split_by_id():
    engine = _engine_with_download_percents({"qbittorrent_1": 60, "qbittorrent_2": 40})
    stats = {
        "qbittorrent_1": {"download_speed": 50.0, "upload_speed": 0.0, "supports_upload": True},
        "qbittorrent_2": {"download_speed": 50.0, "upload_speed": 0.0, "supports_upload": True},
    }
    decisions = engine.calculate_throttle(
        active_streams=[], download_stats=stats, reserved_download_bandwidth_mbps=0.0,
    )
    dl1 = decisions["qbittorrent_1"]["download_limit"]
    dl2 = decisions["qbittorrent_2"]["download_limit"]
    assert dl1 > dl2
    assert dl1 == pytest.approx(60.0, abs=0.5)
    assert dl2 == pytest.approx(40.0, abs=0.5)


def test_two_same_type_upload_clients_split_by_id():
    engine = _engine_with_upload_percents({"qbittorrent_1": 70, "qbittorrent_2": 30})
    stats = {
        "qbittorrent_1": {"download_speed": 0.0, "upload_speed": 25.0, "supports_upload": True},
        "qbittorrent_2": {"download_speed": 0.0, "upload_speed": 25.0, "supports_upload": True},
    }
    decisions = engine.calculate_throttle(
        active_streams=[], download_stats=stats, reserved_bandwidth_mbps=0.0,
    )
    ul1 = decisions["qbittorrent_1"]["upload_limit"]
    ul2 = decisions["qbittorrent_2"]["upload_limit"]
    assert ul1 > ul2
    assert ul1 == pytest.approx(35.0, abs=0.5)
    assert ul2 == pytest.approx(15.0, abs=0.5)


def test_legacy_distinct_type_clients_still_keyed():
    # Legacy clients have id == type; their saved keys must still resolve after re-key.
    engine = _engine_with_download_percents({"qbittorrent": 70, "sabnzbd": 30})
    stats = {
        "qbittorrent": {"download_speed": 50.0, "upload_speed": 0.0, "supports_upload": True},
        "sabnzbd": {"download_speed": 50.0, "upload_speed": 0.0, "supports_upload": False},
    }
    decisions = engine.calculate_throttle(
        active_streams=[], download_stats=stats, reserved_download_bandwidth_mbps=0.0,
    )
    assert decisions["qbittorrent"]["download_limit"] == pytest.approx(70.0, abs=0.5)
    assert decisions["sabnzbd"]["download_limit"] == pytest.approx(30.0, abs=0.5)
