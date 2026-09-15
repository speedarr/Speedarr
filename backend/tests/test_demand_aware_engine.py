"""Demand-aware allocation through calculate_throttle as poll sequences (#85).

100 Mbps download, 50 Mbps upload, two clients, no percents: shares 50/50 (upload 25/25),
safety net 5 (upload 2.5). Poll numbering below counts calls from 1.
"""
import pytest

from app.services.decision_engine import DecisionEngine
from app.services.demand_allocation import DemandState
from tests.conftest import make_config, stats, run, dl, ul


def engine(demand_aware=True, **limits):
    cfg = make_config(**limits)
    cfg.bandwidth.demand_aware_allocation = demand_aware
    return DecisionEngine(cfg)


A_SAT_B_SLACK = stats({"qbittorrent_1": 50.0, "sabnzbd_1": 20.0})


def test_config_default_is_on():
    assert make_config().bandwidth.demand_aware_allocation is True


def test_first_call_is_always_the_target_split():
    d = run(engine(), [A_SAT_B_SLACK])
    assert dl(d, "qbittorrent_1") == pytest.approx(50.0, abs=0.01)
    assert dl(d, "sabnzbd_1") == pytest.approx(50.0, abs=0.01)


def test_squeeze_lands_on_the_fourth_call():
    e = engine()
    for _ in range(3):
        d = run(e, [A_SAT_B_SLACK])
        assert dl(d, "sabnzbd_1") == pytest.approx(50.0, abs=0.01)
    d = run(e, [A_SAT_B_SLACK])  # A SATURATED since call 3, B SLACK on call 4
    assert dl(d, "qbittorrent_1") == pytest.approx(70.0, abs=0.01)
    assert dl(d, "sabnzbd_1") == pytest.approx(30.0, abs=0.01)


def test_give_back_cap_follows_usage_then_full_share_on_second_call():
    e = engine()
    run(e, [A_SAT_B_SLACK] * 4)  # 70 / 30
    d = run(e, [stats({"qbittorrent_1": 50.0, "sabnzbd_1": 30.0})])  # B fills its 30 cap
    assert dl(d, "qbittorrent_1") == pytest.approx(55.0, abs=0.01)
    assert dl(d, "sabnzbd_1") == pytest.approx(45.0, abs=0.01)
    d = run(e, [stats({"qbittorrent_1": 50.0, "sabnzbd_1": 45.0})])  # second high poll: SATURATED
    assert dl(d, "qbittorrent_1") == pytest.approx(50.0, abs=0.01)
    assert dl(d, "sabnzbd_1") == pytest.approx(50.0, abs=0.01)


def test_saturated_client_that_cannot_use_borrowed_share_does_not_cycle():
    # A can only ever pull 48 of its 50 share; B is slack at 20. After the squeeze (70/30) A must
    # stay SATURATED against its own share and the split must hold, poll after poll.
    e = engine()
    polls = [stats({"qbittorrent_1": 48.0, "sabnzbd_1": 20.0})]
    run(e, polls * 4)
    for _ in range(10):
        d = run(e, polls)
        assert dl(d, "qbittorrent_1") == pytest.approx(70.0, abs=0.01)
        assert dl(d, "sabnzbd_1") == pytest.approx(30.0, abs=0.01)
        assert e._demand["download"].state("qbittorrent_1") is DemandState.SATURATED


def test_slack_floor_respects_min_limit_so_pool_is_not_oversubscribed():
    # Pool 50, safety net 2.5 but min_limit_mbps 10: the slack client is held at the effective
    # floor (10) and only 15 is freed, so the flooring pass cannot push the sum above the pool.
    e = engine(download_total=50.0, dl_min=10.0)
    polls = [stats({"qbittorrent_1": 25.0, "sabnzbd_1": 2.2})] * 4
    d = run(e, polls)
    assert dl(d, "qbittorrent_1") == pytest.approx(40.0, abs=0.01)
    assert dl(d, "sabnzbd_1") == pytest.approx(10.0, abs=0.01)
    assert dl(d, "qbittorrent_1") + dl(d, "sabnzbd_1") == pytest.approx(50.0, abs=0.02)


def test_toggle_off_reproduces_fixed_split():
    d = run(engine(demand_aware=False), [A_SAT_B_SLACK] * 6)
    assert dl(d, "qbittorrent_1") == pytest.approx(50.0, abs=0.01)
    assert dl(d, "sabnzbd_1") == pytest.approx(50.0, abs=0.01)


def test_toggle_off_emits_no_demand_log_lines_and_clears_tracker(caplog):
    from loguru import logger as loguru_logger
    e = engine(demand_aware=False)
    handler_id = loguru_logger.add(caplog.handler, level="DEBUG", format="{message}")
    try:
        run(e, [A_SAT_B_SLACK] * 6)
    finally:
        loguru_logger.remove(handler_id)
    assert not any("Demand-aware" in r.getMessage() for r in caplog.records)
    assert e._demand["download"].states() == {}
    assert e._demand["upload"].states() == {}


def test_erroring_client_keeps_target_and_never_lends():
    polls = [stats({"qbittorrent_1": 50.0, "sabnzbd_1": 20.0}, errors=("sabnzbd_1",))] * 6
    d = run(engine(), polls)
    assert dl(d, "qbittorrent_1") == pytest.approx(50.0, abs=0.01)
    assert dl(d, "sabnzbd_1") == pytest.approx(50.0, abs=0.01)


def test_inactive_client_is_not_classified_and_keeps_safety_net():
    e = engine()
    polls = [stats({"qbittorrent_1": 50.0, "sabnzbd_1": 30.0, "nzbget_1": 0.0})] * 6
    # nzbget is SLACK on calls 4-5, then inactive from call 6 and dropped from the tracker;
    # qbittorrent and sabnzbd both stay SATURATED (sabnzbd only goes SLACK on call 8)
    d = run(e, polls)
    assert dl(d, "nzbget_1") == pytest.approx(5.0, abs=0.01)
    assert e._demand["download"].state("nzbget_1") is DemandState.UNKNOWN


def test_removed_client_is_pruned_from_tracker_and_last_emitted():
    e = engine()
    run(e, [A_SAT_B_SLACK] * 4)
    run(e, [stats({"qbittorrent_1": 50.0})])
    assert "sabnzbd_1" not in e._demand["download"].states()
    assert "sabnzbd_1" not in e._last_emitted["download"]


def test_two_client_promotion_at_85_percent_of_cap_with_demand_on():
    e = engine()
    run(e, [stats({"qbittorrent_1": 30.0, "sabnzbd_1": 0.0})] * 6)  # sabnzbd capped at 5.0
    d = run(e, [stats({"qbittorrent_1": 30.0, "sabnzbd_1": 4.25})])
    assert dl(d, "qbittorrent_1") == pytest.approx(50.0, abs=0.01)
    assert dl(d, "sabnzbd_1") == pytest.approx(50.0, abs=0.01)


def test_state_transition_logged_at_info(caplog):
    from loguru import logger as loguru_logger

    handler_id = loguru_logger.add(caplog.handler, level="INFO", format="{message}")
    try:
        run(engine(), [A_SAT_B_SLACK] * 4)
    finally:
        loguru_logger.remove(handler_id)
    messages = [r.getMessage() for r in caplog.records]
    assert any(m.startswith("Demand-aware download: qbittorrent_1 SATURATED") for m in messages)
    assert any("sabnzbd_1 SLACK (20.0 of 50.0 Mbps)" in m and "sabnzbd_1: 30.0 Mbps" in m for m in messages)


# --- upload direction: qbittorrent_1 + transmission_1, 50 Mbps, shares 25/25, safety net 2.5

UP_A_SAT_B_SLACK = stats(upload={"qbittorrent_1": 25.0, "transmission_1": 8.0})


def test_upload_squeeze_lands_on_the_fourth_call():
    e = engine()
    for _ in range(3):
        d = run(e, [UP_A_SAT_B_SLACK])
        assert ul(d, "transmission_1") == pytest.approx(25.0, abs=0.01)
    d = run(e, [UP_A_SAT_B_SLACK])
    assert ul(d, "qbittorrent_1") == pytest.approx(38.0, abs=0.01)
    assert ul(d, "transmission_1") == pytest.approx(12.0, abs=0.01)


def test_upload_toggle_off_reproduces_fixed_split():
    d = run(engine(demand_aware=False), [UP_A_SAT_B_SLACK] * 6)
    assert ul(d, "qbittorrent_1") == pytest.approx(25.0, abs=0.01)
    assert ul(d, "transmission_1") == pytest.approx(25.0, abs=0.01)


def test_usenet_client_never_enters_upload_tracker():
    e = engine()
    run(e, [stats({"sabnzbd_1": 10.0}, upload={"qbittorrent_1": 25.0, "transmission_1": 8.0})] * 4)
    assert "sabnzbd_1" not in e._demand["upload"].states()
    assert "sabnzbd_1" not in e._last_emitted["upload"]


def test_download_and_upload_trackers_are_independent():
    e = engine()
    polls = [stats({"qbittorrent_1": 50.0, "transmission_1": 20.0},
                   upload={"qbittorrent_1": 8.0, "transmission_1": 25.0})] * 4
    d = run(e, polls)
    assert dl(d, "qbittorrent_1") == pytest.approx(70.0, abs=0.01)   # qB saturated on download
    assert ul(d, "transmission_1") == pytest.approx(38.0, abs=0.01)  # transmission saturated on upload


def test_single_upload_client_emits_no_upload_demand_lines(caplog):
    from loguru import logger as loguru_logger
    e = engine()
    handler_id = loguru_logger.add(caplog.handler, level="DEBUG", format="{message}")
    try:
        run(e, [stats({"sabnzbd_1": 10.0}, upload={"qbittorrent_1": 25.0})] * 6)
    finally:
        loguru_logger.remove(handler_id)
    assert not any("Demand-aware upload" in r.getMessage() for r in caplog.records)
    assert e._demand["upload"].states() == {}
