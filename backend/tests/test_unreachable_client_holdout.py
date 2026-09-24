"""Unreachable download clients hold their last limit out of the pool (audit T3-1).

900 Mbps download and 50 Mbps upload unless stated; percents qb 70 / sab 30 where used;
safety net 5% (45 of 900). Poll numbering counts calls from 1. Errored clients are built
with the conftest stats(..., errors=) helper and speed 0, which reads the same as the
controller manager's error dict (no speed keys).
"""
import pytest
from loguru import logger as loguru_logger

from app.constants import HARD_MIN_MBPS
from app.services.decision_engine import DecisionEngine
from tests.conftest import make_config, stats, run, dl, ul


QB, SAB, NZB, TR = "qbittorrent_1", "sabnzbd_1", "nzbget_1", "transmission_1"


def engine(download_total=900.0, upload_total=50.0, percents=None, upload_percents=None,
           demand_aware=True):
    cfg = make_config(download_total=download_total, upload_total=upload_total)
    cfg.bandwidth.demand_aware_allocation = demand_aware
    if percents is not None:
        cfg.bandwidth.download.client_percents = percents
    if upload_percents is not None:
        cfg.bandwidth.upload.upload_client_percents = upload_percents
    return DecisionEngine(cfg)


# --- _hold_outs helper ---------------------------------------------------------

def test_hold_out_is_the_last_emitted_limit_when_there_is_one():
    e = engine()
    e._last_emitted["download"][SAB] = 45.0
    held = e._hold_outs("download", [SAB], [QB, SAB], 900.0, {QB: 70, SAB: 30})
    assert held == {SAB: 45.0}


def test_hold_out_is_the_configured_share_when_nothing_was_emitted():
    held = engine()._hold_outs("download", [SAB], [QB, SAB], 900.0, {QB: 70, SAB: 30})
    assert held[SAB] == pytest.approx(270.0)


def test_hold_out_is_the_equal_split_without_percents():
    held = engine()._hold_outs("download", [NZB], [QB, SAB, NZB], 900.0, {})
    assert held[NZB] == pytest.approx(300.0)


def test_hold_out_falls_back_to_equal_split_on_partial_or_zero_percents():
    e = engine()
    assert e._hold_outs("download", [SAB], [QB, SAB], 900.0, {QB: 70})[SAB] == pytest.approx(450.0)
    assert e._hold_outs("download", [SAB], [QB, SAB], 900.0, {QB: 0, SAB: 0})[SAB] == pytest.approx(450.0)


def test_hold_outs_mix_last_emitted_and_configured_share_per_client():
    e = engine()
    e._last_emitted["download"][SAB] = 45.0
    held = e._hold_outs("download", [SAB, NZB], [QB, SAB, NZB], 900.0, {})
    assert held[SAB] == 45.0
    assert held[NZB] == pytest.approx(300.0)


def test_hold_outs_read_the_table_of_their_own_direction():
    e = engine()
    e._last_emitted["download"][QB] = 630.0
    e._last_emitted["upload"][QB] = 35.0
    assert e._hold_outs("upload", [QB], [QB, TR], 50.0, {}) == {QB: 35.0}


def test_no_errored_clients_means_no_hold_outs():
    assert engine()._hold_outs("download", [], [QB, SAB], 900.0, {}) == {}


# --- download path -------------------------------------------------------------

BOTH_BUSY = stats({QB: 600.0, SAB: 200.0})
SAB_DOWN = stats({QB: 600.0, SAB: 0.0}, errors=(SAB,))
QB_BUSY_SAB_IDLE = stats({QB: 600.0, SAB: 0.0})


def both(d, qb, sab):
    assert dl(d, QB) == pytest.approx(qb, abs=0.01)
    assert dl(d, SAB) == pytest.approx(sab, abs=0.01)


def test_reproduction_errored_client_holds_its_share_across_the_sixth_poll():
    # Verifier's case: qb downloading, sab returning the error dict. Today the split holds
    # 630/270 for five errored polls and moves to 855/45 on the sixth.
    e = engine(percents={QB: 70, SAB: 30})
    both(run(e, [BOTH_BUSY]), 630.0, 270.0)
    for poll in range(2, 12):
        d = run(e, [SAB_DOWN])
        assert dl(d, QB) == pytest.approx(630.0, abs=0.01), f"poll {poll}"
        assert dl(d, SAB) == pytest.approx(270.0, abs=0.01), f"poll {poll}"


def test_hold_out_is_the_safety_net_when_the_client_went_unreachable_idle():
    e = engine(percents={QB: 70, SAB: 30})
    both(run(e, [QB_BUSY_SAB_IDLE] * 7), 855.0, 45.0)   # sab inactive from poll 6
    both(run(e, [SAB_DOWN] * 3), 855.0, 45.0)           # holds 45, not its 30% share


def test_hold_out_is_the_lent_down_limit_after_a_demand_aware_borrow():
    e = engine(download_total=100.0)
    both(run(e, [stats({QB: 50.0, SAB: 20.0})] * 4), 70.0, 30.0)   # sab SLACK on call 4
    both(run(e, [stats({QB: 50.0, SAB: 0.0}, errors=(SAB,))] * 3), 70.0, 30.0)


def test_since_start_holds_the_configured_share_with_percents():
    both(run(engine(percents={QB: 70, SAB: 30}), [SAB_DOWN]), 630.0, 270.0)


def test_since_start_holds_the_equal_split_without_percents():
    both(run(engine(), [SAB_DOWN]), 450.0, 450.0)


def test_since_start_three_clients_no_percents():
    d = run(engine(), [stats({QB: 600.0, SAB: 200.0, NZB: 0.0}, errors=(NZB,))])
    assert dl(d, NZB) == pytest.approx(300.0, abs=0.01)
    assert dl(d, QB) == pytest.approx(300.0, abs=0.01)
    assert dl(d, SAB) == pytest.approx(300.0, abs=0.01)


def test_since_start_share_stays_fixed_when_a_reserve_lowers_available():
    e = engine(percents={QB: 70, SAB: 30})
    both(run(e, [SAB_DOWN]), 630.0, 270.0)
    d = e.calculate_throttle(active_streams=[], download_stats=SAB_DOWN,
                             reserved_download_bandwidth_mbps=200.0)
    both(d, 430.0, 270.0)   # 700 available, 270 still held


def test_temporary_limit_lowers_the_pool_but_not_the_hold():
    e = engine(percents={QB: 70, SAB: 30})
    run(e, [BOTH_BUSY])                                  # 630 / 270 emitted
    d = e.calculate_throttle(active_streams=[], download_stats=SAB_DOWN, temp_download_limit=500.0)
    both(d, 230.0, 270.0)                                # the hold does not follow the total (spec 4.5)


def test_since_start_during_zero_available_is_held_at_the_floor_until_it_answers():
    e = engine(percents={QB: 70, SAB: 30})
    d = e.calculate_throttle(active_streams=[], download_stats=SAB_DOWN,
                             reserved_download_bandwidth_mbps=900.0)
    assert dl(d, SAB) == pytest.approx(1.0, abs=0.01)   # 30% of 0, floored to min_limit_mbps
    both(run(e, [SAB_DOWN]), 899.0, 1.0)                 # reserve gone: the hold stays (spec 4.5)


def test_hold_out_at_or_above_available_floors_the_reachable_client():
    e = engine(percents={QB: 70, SAB: 30})
    run(e, [BOTH_BUSY])                                  # 630 / 270 emitted
    d = e.calculate_throttle(active_streams=[], download_stats=SAB_DOWN,
                             reserved_download_bandwidth_mbps=700.0)
    assert dl(d, SAB) == pytest.approx(270.0, abs=0.01)
    assert dl(d, QB) == pytest.approx(max(1.0, HARD_MIN_MBPS), abs=0.01)   # 200 − 270 < 0 → floor


def test_recovery_downloading_resumes_the_normal_split_at_once():
    e = engine(percents={QB: 70, SAB: 30})
    run(e, [BOTH_BUSY])
    run(e, [SAB_DOWN] * 8)
    both(run(e, [BOTH_BUSY]), 630.0, 270.0)


def test_recovery_idle_after_a_long_outage_lands_on_the_safety_net_at_once():
    e = engine(percents={QB: 70, SAB: 30})
    run(e, [BOTH_BUSY])
    run(e, [SAB_DOWN] * 8)                               # counter climbs past the buffer while held
    both(run(e, [QB_BUSY_SAB_IDLE]), 855.0, 45.0)


def test_recovery_idle_after_a_short_outage_stays_inside_the_buffer():
    e = engine(percents={QB: 70, SAB: 30})
    run(e, [BOTH_BUSY])
    run(e, [SAB_DOWN] * 2)                               # counter 2 while held
    both(run(e, [QB_BUSY_SAB_IDLE]), 630.0, 270.0)       # counter 3 < 6: still active, like a dip


def test_errored_client_gets_a_decision_every_poll_and_its_last_emitted_does_not_move():
    e = engine(percents={QB: 70, SAB: 30})
    run(e, [BOTH_BUSY])
    for _ in range(8):                                   # past the sixth errored poll
        d = run(e, [SAB_DOWN])
        assert d[SAB]["action"] == "throttle"
        assert d[SAB]["download_limit"] == pytest.approx(270.0, abs=0.01)
        assert e._last_emitted["download"][SAB] == pytest.approx(270.0, abs=0.01)


def test_every_client_errored_gives_every_client_its_hold_out():
    e = engine(percents={QB: 70, SAB: 30})
    both(run(e, [stats({QB: 0.0, SAB: 0.0}, errors=(QB, SAB))] * 8), 630.0, 270.0)   # past the buffer


def test_minimal_error_dict_shapes_do_not_crash_any_path():
    # The controller manager's real shape (no speed keys) and the bare shape it produces
    # when client_config is None (no supports_upload either).
    e = engine()
    poll = {
        QB: {"download_speed": 600.0, "upload_speed": 0.0, "supports_upload": True},
        SAB: {"active": False, "error": "Cannot connect to host sabnzbd:8080",
              "client_type": "sabnzbd", "client_name": "SABnzbd", "supports_upload": False},
        NZB: {"error": "boom"},
    }
    d = run(e, [poll] * 7)
    assert dl(d, SAB) == pytest.approx(300.0, abs=0.01)
    assert dl(d, NZB) == pytest.approx(300.0, abs=0.01)
    assert dl(d, QB) == pytest.approx(300.0, abs=0.01)
    assert ul(d, SAB) == 0 and ul(d, NZB) == 0


# --- SNMP ----------------------------------------------------------------------

def test_snmp_credits_the_hold_out_as_managed_traffic():
    e = engine(percents={QB: 70, SAB: 30})
    run(e, [BOTH_BUSY])                                  # sab's last limit: 270
    snmp = {"download": 870.0, "upload": 0.0}            # qb 500 + sab 270 (unseen) + other devices 100
    poll = stats({QB: 500.0, SAB: 0.0}, errors=(SAB,))
    d = e.calculate_throttle(active_streams=[], download_stats=poll, snmp_data=snmp)
    assert dl(d, SAB) == pytest.approx(270.0, abs=0.01)
    assert dl(d, QB) == pytest.approx(530.0, abs=0.01)   # 900 − 100 other − 270 held; not 260


def test_snmp_without_errored_clients_is_unchanged():
    e = engine(percents={QB: 70, SAB: 30})
    snmp = {"download": 900.0, "upload": 0.0}            # qb 600 + sab 200 + other devices 100
    d = e.calculate_throttle(active_streams=[], download_stats=BOTH_BUSY, snmp_data=snmp)
    both(d, 560.0, 240.0)                                # 800 split 70/30


# --- upload mirror -------------------------------------------------------------

def test_errored_torrent_client_holds_its_last_upload_limit():
    e = engine()
    both_up = stats({QB: 100.0, TR: 100.0, SAB: 50.0}, upload={QB: 20.0, TR: 20.0})
    d = run(e, [both_up])
    assert ul(d, QB) == pytest.approx(25.0, abs=0.01)
    assert ul(d, TR) == pytest.approx(25.0, abs=0.01)
    tr_down = stats({QB: 100.0, TR: 0.0, SAB: 50.0}, upload={QB: 20.0}, errors=(TR,))
    d = run(e, [tr_down] * 8)
    assert ul(d, TR) == pytest.approx(25.0, abs=0.01)    # held, not the 2.5 safety net
    assert ul(d, QB) == pytest.approx(25.0, abs=0.01)    # the rest, not 47.5
    assert ul(d, SAB) == 0
    assert dl(d, TR) == pytest.approx(300.0, abs=0.01)   # download hold-out from poll 1's equal split


def test_upload_since_start_holds_the_configured_upload_share():
    e = engine(upload_percents={QB: 60, TR: 40})
    d = run(e, [stats({QB: 100.0, TR: 0.0}, upload={QB: 20.0}, errors=(TR,))] * 8)   # past the buffer
    assert ul(d, TR) == pytest.approx(20.0, abs=0.01)    # 40% of 50, frozen; not the 2.5 safety net
    assert ul(d, QB) == pytest.approx(30.0, abs=0.01)


def test_upload_hold_out_above_available_floors_the_reachable_client():
    e = engine()
    run(e, [stats({QB: 100.0, TR: 100.0}, upload={QB: 20.0, TR: 20.0})])   # 25 / 25 emitted
    poll = stats({QB: 100.0, TR: 0.0}, upload={QB: 20.0}, errors=(TR,))
    d = e.calculate_throttle(active_streams=[], download_stats=poll, reserved_bandwidth_mbps=45.0)
    assert ul(d, TR) == pytest.approx(25.0, abs=0.01)
    assert ul(d, QB) == pytest.approx(max(1.0, HARD_MIN_MBPS), abs=0.01)   # 5 − 25 < 0 → floor


# --- transition logging --------------------------------------------------------

@pytest.fixture
def engine_log(caplog):
    handler_id = loguru_logger.add(caplog.handler, level="INFO", format="{message}")
    yield caplog
    loguru_logger.remove(handler_id)


def hold_lines(caplog):
    return [r.getMessage() for r in caplog.records
            if "holding its" in r.getMessage() or "reachable again" in r.getMessage()]


def test_one_line_on_entering_none_while_held_one_on_return(engine_log):
    e = engine(percents={QB: 70, SAB: 30})
    run(e, [BOTH_BUSY])
    run(e, [SAB_DOWN] * 4)
    run(e, [BOTH_BUSY])
    assert hold_lines(engine_log) == [
        "sabnzbd_1 unreachable: holding its last limits out of the pool (download 270.0 Mbps)",
        "sabnzbd_1 reachable again: back in the split",
    ]


def test_since_start_wording_and_upload_figure_for_a_torrent_client(engine_log):
    e = engine(percents={QB: 70, SAB: 30})
    run(e, [stats({QB: 0.0, SAB: 200.0}, errors=(QB,))])
    assert hold_lines(engine_log) == [
        "qbittorrent_1 unreachable since start: holding its configured share out of the pool "
        "(download 630.0 Mbps, upload 50.0 Mbps)",
    ]


def test_a_client_removed_while_held_logs_nothing_and_is_forgotten(engine_log):
    e = engine()
    run(e, [QB_BUSY_SAB_IDLE])
    run(e, [SAB_DOWN])
    run(e, [stats({QB: 600.0})])                          # sab removed from the configuration
    assert hold_lines(engine_log) == [
        "sabnzbd_1 unreachable: holding its last limits out of the pool (download 450.0 Mbps)",
    ]
    assert SAB not in e._held
    assert SAB not in e._last_emitted["download"]


def test_a_second_outage_logs_a_fresh_pair(engine_log):
    e = engine(percents={QB: 70, SAB: 30})
    run(e, [BOTH_BUSY, SAB_DOWN, BOTH_BUSY, SAB_DOWN, SAB_DOWN])
    lines = hold_lines(engine_log)
    assert len(lines) == 3
    assert lines[0].startswith("sabnzbd_1 unreachable: ")
    assert lines[1] == "sabnzbd_1 reachable again: back in the split"
    assert lines[2].startswith("sabnzbd_1 unreachable: ")


def test_a_poll_with_no_clients_forgets_held_clients(engine_log):
    e = engine()
    run(e, [QB_BUSY_SAB_IDLE])
    run(e, [SAB_DOWN])                                    # sab held (450 last emitted)
    run(e, [{}])                                          # every client removed
    assert e._held == set()
    run(e, [SAB_DOWN])                                    # sab re-added, still unreachable
    lines = hold_lines(engine_log)
    assert len(lines) == 2
    assert lines[0] == "sabnzbd_1 unreachable: holding its last limits out of the pool (download 450.0 Mbps)"
    assert lines[1].startswith("sabnzbd_1 unreachable: ")   # a fresh hold line, never "reachable again"
