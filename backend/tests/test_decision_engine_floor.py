"""Per-client throttle floor in the decision engine (issue #43)."""
from app.services.decision_engine import HARD_MIN_MBPS
from tests.conftest import make_stats


# --- _floor unit behavior ---

def test_floor_value_above_min_unchanged(make_engine):
    assert make_engine()._floor(10.0, 1.0) == 10.0


def test_floor_value_below_min_raised_to_min(make_engine):
    assert make_engine()._floor(0.5, 1.0) == 1.0


def test_floor_zero_with_positive_min_uses_min(make_engine):
    assert make_engine()._floor(0.0, 1.0) == 1.0


def test_floor_zero_with_min_zero_uses_hard_min(make_engine):
    assert make_engine()._floor(0.0, 0.0) == HARD_MIN_MBPS


# --- calculate_throttle scenarios (no streams; reservation params drive availability) ---

def test_upload_floored_when_reservation_equals_ceiling(make_engine):
    engine = make_engine(upload_total=50.0, ul_min=1.0)
    decisions = engine.calculate_throttle(
        active_streams=[],
        download_stats=make_stats(),
        reserved_bandwidth_mbps=50.0,  # equals upload ceiling -> available_upload == 0
    )
    assert decisions["qbittorrent_1"]["upload_limit"] == 1.0
    assert decisions["sabnzbd_1"]["upload_limit"] == 0  # usenet: no upload floor


def test_upload_floored_when_reservation_exceeds_ceiling(make_engine):
    engine = make_engine(upload_total=50.0, ul_min=1.0)
    decisions = engine.calculate_throttle(
        active_streams=[],
        download_stats=make_stats(),
        reserved_bandwidth_mbps=80.0,  # exceeds ceiling
    )
    assert decisions["qbittorrent_1"]["upload_limit"] == 1.0


def test_upload_trickle_when_min_zero(make_engine):
    engine = make_engine(upload_total=50.0, ul_min=0.0)
    decisions = engine.calculate_throttle(
        active_streams=[],
        download_stats=make_stats(),
        reserved_bandwidth_mbps=50.0,
    )
    assert decisions["qbittorrent_1"]["upload_limit"] == HARD_MIN_MBPS  # never 0/unlimited


def test_download_floored_for_all_clients(make_engine):
    engine = make_engine(download_total=100.0, dl_min=1.0)
    decisions = engine.calculate_throttle(
        active_streams=[],
        download_stats=make_stats(),
        reserved_download_bandwidth_mbps=100.0,  # consumes all download
    )
    assert decisions["qbittorrent_1"]["download_limit"] == 1.0
    assert decisions["sabnzbd_1"]["download_limit"] == 1.0


def test_normal_upload_allocation_not_floored(make_engine):
    engine = make_engine(upload_total=50.0, ul_min=1.0)
    decisions = engine.calculate_throttle(
        active_streams=[],
        download_stats=make_stats(),
        reserved_bandwidth_mbps=0.0,  # full upload available
    )
    # single upload client receives the full available upload, well above the floor
    assert decisions["qbittorrent_1"]["upload_limit"] == 50.0
