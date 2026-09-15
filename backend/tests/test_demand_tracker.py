"""DemandTracker: per-client SATURATED / SLACK classification (#85)."""
from app.services.demand_allocation import (
    DemandState,
    DemandTracker,
    DEMAND_POLLS_TO_SATURATED,
    DEMAND_POLLS_TO_SLACK,
    DEMAND_SATURATION_RATIO,
)


def feed(tracker, cid, ratios, limit=100.0):
    """Observe a sequence of speed/limit ratios; return the final state."""
    state = tracker.state(cid)
    for r in ratios:
        state = tracker.observe(cid, r * limit, limit)
    return state


def test_constants_match_spec():
    assert DEMAND_SATURATION_RATIO == 0.9
    assert DEMAND_POLLS_TO_SATURATED == 2
    assert DEMAND_POLLS_TO_SLACK == 3


def test_unknown_client_is_unknown():
    assert DemandTracker().state("a") is DemandState.UNKNOWN


def test_two_polls_at_ratio_become_saturated():
    t = DemandTracker()
    assert feed(t, "a", [0.9]) is DemandState.UNKNOWN
    assert feed(t, "a", [0.9]) is DemandState.SATURATED


def test_three_polls_below_ratio_become_slack():
    t = DemandTracker()
    assert feed(t, "a", [0.5, 0.5]) is DemandState.UNKNOWN
    assert feed(t, "a", [0.5]) is DemandState.SLACK


def test_saturated_holds_through_two_low_polls_and_flips_on_third():
    t = DemandTracker()
    feed(t, "a", [1.0, 1.0])
    assert feed(t, "a", [0.3, 0.3]) is DemandState.SATURATED
    assert feed(t, "a", [0.3]) is DemandState.SLACK


def test_slack_holds_through_one_high_poll_and_flips_on_second():
    t = DemandTracker()
    feed(t, "a", [0.3, 0.3, 0.3])
    assert feed(t, "a", [1.0]) is DemandState.SLACK
    assert feed(t, "a", [1.0]) is DemandState.SATURATED


def test_crossing_resets_the_opposite_counter():
    t = DemandTracker()
    feed(t, "a", [0.3, 0.3])          # down = 2
    feed(t, "a", [1.0])               # up = 1, down reset
    assert feed(t, "a", [0.3, 0.3]) is DemandState.UNKNOWN  # down = 2 again, not 4


def test_single_spike_does_not_promote():
    t = DemandTracker()
    feed(t, "a", [0.3, 0.3, 0.3])     # SLACK
    assert feed(t, "a", [4.4]) is DemandState.SLACK
    assert feed(t, "a", [0.3]) is DemandState.SLACK


def test_none_or_zero_last_limit_resets_to_unknown():
    t = DemandTracker()
    feed(t, "a", [1.0, 1.0])
    assert t.observe("a", 50.0, None) is DemandState.UNKNOWN
    feed(t, "a", [1.0, 1.0])
    assert t.observe("a", 50.0, 0.0) is DemandState.UNKNOWN
    assert feed(t, "a", [1.0]) is DemandState.UNKNOWN  # counters were cleared


def test_reset_clears_state_and_counters():
    t = DemandTracker()
    feed(t, "a", [1.0, 1.0])
    t.reset("a")
    assert t.state("a") is DemandState.UNKNOWN
    assert feed(t, "a", [1.0]) is DemandState.UNKNOWN


def test_prune_drops_clients_not_in_current_set():
    t = DemandTracker()
    feed(t, "a", [1.0, 1.0])
    feed(t, "b", [1.0, 1.0])
    t.prune(["a"])
    assert set(t.states()) == {"a"}
    assert t.state("b") is DemandState.UNKNOWN


def test_states_snapshot_is_a_copy():
    t = DemandTracker()
    feed(t, "a", [1.0, 1.0])
    snap = t.states()
    feed(t, "a", [0.1, 0.1, 0.1])
    assert snap["a"] is DemandState.SATURATED
    assert t.state("a") is DemandState.SLACK


def test_clients_are_independent():
    t = DemandTracker()
    feed(t, "a", [1.0, 1.0])
    assert feed(t, "b", [0.2, 0.2, 0.2]) is DemandState.SLACK
    assert t.state("a") is DemandState.SATURATED
