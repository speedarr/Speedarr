"""Characterisation of the allocation branches as they behave at fc51c67.

These pin today's numbers so the #85 refactor can be proved neutral. Every test
here must pass unchanged before and after the refactor, except the one marked
"changes in Task 3" (promotion-threshold cap).
"""
import pytest

from app.services.decision_engine import DecisionEngine
from tests.conftest import make_config, stats, run, dl, ul

# Every case below is a pure-split characterisation, so it must hold with demand-aware
# allocation on and off; the autouse fixture runs the whole module both ways (issue #85).
_DEMAND_AWARE = True


@pytest.fixture(autouse=True, params=[True, False], ids=["demand_on", "demand_off"])
def _demand_toggle(request):
    global _DEMAND_AWARE
    _DEMAND_AWARE = request.param
    yield
    _DEMAND_AWARE = True


def engine_with(download_total=100.0, upload_total=50.0, percents=None, upload_percents=None):
    cfg = make_config(download_total=download_total, upload_total=upload_total)
    cfg.bandwidth.demand_aware_allocation = _DEMAND_AWARE
    if percents is not None:
        cfg.bandwidth.download.client_percents = percents
    if upload_percents is not None:
        cfg.bandwidth.upload.upload_client_percents = upload_percents
    return DecisionEngine(cfg)


# --- startup quirk -----------------------------------------------------------

def test_fresh_engine_treats_every_client_as_active_for_five_polls():
    engine = engine_with(percents={"qbittorrent_1": 70, "sabnzbd_1": 30})
    idle = stats({"qbittorrent_1": 0, "sabnzbd_1": 0})
    for _ in range(5):
        d = run(engine, [idle])
        assert dl(d, "qbittorrent_1") == pytest.approx(70.0, abs=0.01)
        assert dl(d, "sabnzbd_1") == pytest.approx(30.0, abs=0.01)
    d = run(engine, [idle])  # sixth poll: both inactive -> standby equal split
    assert dl(d, "qbittorrent_1") == pytest.approx(50.0, abs=0.01)
    assert dl(d, "sabnzbd_1") == pytest.approx(50.0, abs=0.01)


# --- download branches -------------------------------------------------------

def test_standby_equal_split_two_clients():
    engine = engine_with()
    d = run(engine, [stats({"qbittorrent_1": 0, "sabnzbd_1": 0})] * 6)
    assert dl(d, "qbittorrent_1") == pytest.approx(50.0, abs=0.01)
    assert dl(d, "sabnzbd_1") == pytest.approx(50.0, abs=0.01)


def test_single_active_two_clients_95_5():
    engine = engine_with()
    d = run(engine, [stats({"qbittorrent_1": 30, "sabnzbd_1": 0})] * 6)
    assert dl(d, "qbittorrent_1") == pytest.approx(95.0, abs=0.01)
    assert dl(d, "sabnzbd_1") == pytest.approx(5.0, abs=0.01)


def test_single_active_three_clients_90_5_5():
    engine = engine_with()
    d = run(engine, [stats({"qbittorrent_1": 30, "sabnzbd_1": 0, "nzbget_1": 0})] * 6)
    assert dl(d, "qbittorrent_1") == pytest.approx(90.0, abs=0.01)
    assert dl(d, "sabnzbd_1") == pytest.approx(5.0, abs=0.01)
    assert dl(d, "nzbget_1") == pytest.approx(5.0, abs=0.01)


def test_multiple_active_equal_when_no_percents():
    engine = engine_with()
    d = run(engine, [stats({"qbittorrent_1": 30, "sabnzbd_1": 30})])
    assert dl(d, "qbittorrent_1") == pytest.approx(50.0, abs=0.01)
    assert dl(d, "sabnzbd_1") == pytest.approx(50.0, abs=0.01)


def test_multiple_active_by_percents_when_all_configured():
    engine = engine_with(percents={"qbittorrent_1": 70, "sabnzbd_1": 30})
    d = run(engine, [stats({"qbittorrent_1": 30, "sabnzbd_1": 30})])
    assert dl(d, "qbittorrent_1") == pytest.approx(70.0, abs=0.01)
    assert dl(d, "sabnzbd_1") == pytest.approx(30.0, abs=0.01)


def test_multiple_active_equal_when_percents_partial():
    engine = engine_with(percents={"qbittorrent_1": 70})
    d = run(engine, [stats({"qbittorrent_1": 30, "sabnzbd_1": 30})])
    assert dl(d, "qbittorrent_1") == pytest.approx(50.0, abs=0.01)
    assert dl(d, "sabnzbd_1") == pytest.approx(50.0, abs=0.01)


def test_multiple_active_equal_when_percents_sum_zero():
    engine = engine_with(percents={"qbittorrent_1": 0, "sabnzbd_1": 0})
    d = run(engine, [stats({"qbittorrent_1": 30, "sabnzbd_1": 30})])
    assert dl(d, "qbittorrent_1") == pytest.approx(50.0, abs=0.01)
    assert dl(d, "sabnzbd_1") == pytest.approx(50.0, abs=0.01)


def test_multiple_active_with_inactive_third_gets_safety_net():
    engine = engine_with()
    d = run(engine, [stats({"qbittorrent_1": 30, "sabnzbd_1": 30, "nzbget_1": 0})] * 6)
    assert dl(d, "qbittorrent_1") == pytest.approx(47.5, abs=0.01)
    assert dl(d, "sabnzbd_1") == pytest.approx(47.5, abs=0.01)
    assert dl(d, "nzbget_1") == pytest.approx(5.0, abs=0.01)


def test_allocations_sum_to_available_in_every_branch():
    engine = engine_with()
    polls = [stats({"qbittorrent_1": 30, "sabnzbd_1": 30, "nzbget_1": 0})] * 6
    for poll in polls:
        d = run(engine, [poll])
        assert sum(dl(d, c) for c in d) == pytest.approx(100.0, abs=0.05)


# --- inactive buffer ---------------------------------------------------------

def test_inactive_buffer_keeps_client_active_for_five_polls_then_drops():
    engine = engine_with()
    run(engine, [stats({"qbittorrent_1": 30, "sabnzbd_1": 30})])  # both genuinely active
    dropped = stats({"qbittorrent_1": 30, "sabnzbd_1": 0})
    for _ in range(5):
        d = run(engine, [dropped])
        assert dl(d, "sabnzbd_1") == pytest.approx(50.0, abs=0.01)  # still within buffer
    d = run(engine, [dropped])  # sixth poll below threshold -> inactive
    assert dl(d, "qbittorrent_1") == pytest.approx(95.0, abs=0.01)
    assert dl(d, "sabnzbd_1") == pytest.approx(5.0, abs=0.01)


def test_speed_above_threshold_resets_inactive_counter():
    engine = engine_with()
    dropped = stats({"qbittorrent_1": 30, "sabnzbd_1": 0})
    run(engine, [dropped] * 4)
    run(engine, [stats({"qbittorrent_1": 30, "sabnzbd_1": 30})])  # resets counter
    for _ in range(5):
        d = run(engine, [dropped])
        assert dl(d, "sabnzbd_1") == pytest.approx(50.0, abs=0.01)


# --- promotion of a capped client (2 clients: cap 5.0, threshold 5.0) ---------

def _capped_engine():
    engine = engine_with()
    run(engine, [stats({"qbittorrent_1": 30, "sabnzbd_1": 0})] * 6)  # sabnzbd inactive, capped at 5.0
    return engine


def test_capped_client_at_80_percent_of_cap_not_promoted():
    d = run(_capped_engine(), [stats({"qbittorrent_1": 30, "sabnzbd_1": 4.0})])
    assert dl(d, "sabnzbd_1") == pytest.approx(5.0, abs=0.01)


def test_capped_client_above_standby_threshold_promoted():
    d = run(_capped_engine(), [stats({"qbittorrent_1": 30, "sabnzbd_1": 5.01})])
    assert dl(d, "qbittorrent_1") == pytest.approx(50.0, abs=0.01)
    assert dl(d, "sabnzbd_1") == pytest.approx(50.0, abs=0.01)


def test_capped_client_at_90_percent_of_cap_is_promoted():
    # Threshold is min(10% of standby, 80% of the safety net) = min(5.0, 4.0) = 4.0,
    # so a capped client no longer depends on limiter overshoot to be promoted.
    d = run(_capped_engine(), [stats({"qbittorrent_1": 30, "sabnzbd_1": 4.5})])
    assert dl(d, "qbittorrent_1") == pytest.approx(50.0, abs=0.01)
    assert dl(d, "sabnzbd_1") == pytest.approx(50.0, abs=0.01)


# --- upload branches (upload_total 50: standby 25 each, safety net 2.5) --------

def test_upload_usenet_client_gets_zero_upload_limit():
    engine = engine_with()
    d = run(engine, [stats({"qbittorrent_1": 0, "sabnzbd_1": 0}, upload={"qbittorrent_1": 20})])
    assert ul(d, "sabnzbd_1") == 0


def test_upload_multiple_active_equal_split():
    engine = engine_with()
    d = run(engine, [stats(upload={"qbittorrent_1": 20, "transmission_1": 20})])
    assert ul(d, "qbittorrent_1") == pytest.approx(25.0, abs=0.01)
    assert ul(d, "transmission_1") == pytest.approx(25.0, abs=0.01)


def test_upload_multiple_active_by_upload_percents():
    engine = engine_with(upload_percents={"qbittorrent_1": 70, "transmission_1": 30})
    d = run(engine, [stats(upload={"qbittorrent_1": 20, "transmission_1": 20})])
    assert ul(d, "qbittorrent_1") == pytest.approx(35.0, abs=0.01)
    assert ul(d, "transmission_1") == pytest.approx(15.0, abs=0.01)


def test_upload_single_active_95_5_after_buffer():
    engine = engine_with()
    d = run(engine, [stats(upload={"qbittorrent_1": 20, "transmission_1": 0})] * 6)
    assert ul(d, "qbittorrent_1") == pytest.approx(47.5, abs=0.01)
    assert ul(d, "transmission_1") == pytest.approx(2.5, abs=0.01)


def test_upload_inactive_buffer_five_polls():
    engine = engine_with()
    run(engine, [stats(upload={"qbittorrent_1": 20, "transmission_1": 20})])
    dropped = stats(upload={"qbittorrent_1": 20, "transmission_1": 0})
    for _ in range(5):
        d = run(engine, [dropped])
        assert ul(d, "transmission_1") == pytest.approx(25.0, abs=0.01)
    d = run(engine, [dropped])
    assert ul(d, "transmission_1") == pytest.approx(2.5, abs=0.01)


def test_upload_standby_equal_split_after_buffer():
    engine = engine_with()
    d = run(engine, [stats(upload={"qbittorrent_1": 0, "transmission_1": 0})] * 6)
    assert ul(d, "qbittorrent_1") == pytest.approx(25.0, abs=0.01)
    assert ul(d, "transmission_1") == pytest.approx(25.0, abs=0.01)


def test_upload_capped_client_at_90_percent_of_cap_is_promoted():
    engine = engine_with()
    run(engine, [stats(upload={"qbittorrent_1": 20, "transmission_1": 0})] * 6)  # transmission capped at 2.5
    d = run(engine, [stats(upload={"qbittorrent_1": 20, "transmission_1": 2.25})])
    assert ul(d, "qbittorrent_1") == pytest.approx(25.0, abs=0.01)
    assert ul(d, "transmission_1") == pytest.approx(25.0, abs=0.01)
