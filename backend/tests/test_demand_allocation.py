"""Pure demand-allocation helpers (#85)."""
import pytest

from app.services.demand_allocation import split_weights, apply_demand, DemandState


def test_split_weights_uses_percents_when_all_configured():
    assert split_weights(["a", "b"], {"a": 70, "b": 30}) == {"a": pytest.approx(0.7), "b": pytest.approx(0.3)}


def test_split_weights_normalises_percents_that_do_not_sum_to_100():
    w = split_weights(["a", "b", "c"], {"a": 50, "b": 20, "c": 10})
    assert w["a"] == pytest.approx(0.625)
    assert sum(w.values()) == pytest.approx(1.0)


def test_split_weights_equal_when_any_active_client_unconfigured():
    assert split_weights(["a", "b"], {"a": 70}) == {"a": 0.5, "b": 0.5}


def test_split_weights_equal_when_percents_sum_to_zero():
    assert split_weights(["a", "b"], {"a": 0, "b": 0}) == {"a": 0.5, "b": 0.5}


def test_split_weights_ignores_percents_of_inactive_clients():
    assert split_weights(["a"], {"a": 30, "b": 70}) == {"a": 1.0}


def test_split_weights_empty_active_returns_empty():
    assert split_weights([], {"a": 30}) == {}


S, K, U = DemandState.SATURATED, DemandState.SLACK, DemandState.UNKNOWN


def approx_dict(d):
    return {k: pytest.approx(v, abs=0.01) for k, v in d.items()}


# --- spec 3.1: two clients, 900 Mbps, 50/50, safety net 45 -------------------

def test_two_clients_a_saturated_b_slack_at_40():
    out = apply_demand({"a": 450, "b": 450}, {"a": S, "b": K}, {"a": 450, "b": 40}, {}, 45, True)
    assert out == approx_dict({"a": 840, "b": 60})


def test_two_clients_b_slack_at_100_keeps_150():
    out = apply_demand({"a": 450, "b": 450}, {"a": S, "b": K}, {"a": 450, "b": 100}, {}, 45, True)
    assert out == approx_dict({"a": 750, "b": 150})


def test_slack_client_below_floor_gets_safety_net():
    out = apply_demand({"a": 450, "b": 450}, {"a": S, "b": K}, {"a": 450, "b": 10}, {}, 45, True)
    assert out == approx_dict({"a": 855, "b": 45})


def test_dead_band_two_thirds_of_share_is_never_squeezed():
    out = apply_demand({"a": 450, "b": 450}, {"a": S, "b": K}, {"a": 450, "b": 300}, {}, 45, True)
    assert out == approx_dict({"a": 450, "b": 450})


def test_slack_cap_follows_usage_up_before_promotion():
    # B squeezed to 60 starts pulling and reads 60: still SLACK, its cap rises to 90.
    out = apply_demand({"a": 450, "b": 450}, {"a": S, "b": K}, {"a": 810, "b": 60}, {}, 45, True)
    assert out == approx_dict({"a": 810, "b": 90})


# --- spec 3.1: three clients 50/30/20 on 900, safety net 45 -------------------

def test_three_clients_two_slack_one_saturated():
    target = {"qb": 450, "tr": 270, "sab": 180}
    states = {"qb": K, "tr": K, "sab": S}
    speeds = {"qb": 100, "tr": 20, "sab": 180}
    out = apply_demand(target, states, speeds, {"qb": 50, "tr": 30, "sab": 20}, 45, True)
    assert out == approx_dict({"qb": 150, "tr": 45, "sab": 705})


def test_freed_share_weighted_by_percents_of_saturated_clients():
    target = {"qb": 450, "tr": 270, "sab": 180}
    states = {"qb": S, "tr": K, "sab": S}
    speeds = {"qb": 450, "tr": 20, "sab": 180}
    out = apply_demand(target, states, speeds, {"qb": 50, "tr": 30, "sab": 20}, 45, True)
    assert out == approx_dict({"qb": 610.71, "tr": 45, "sab": 244.29})


def test_freed_share_equal_when_saturated_percents_partial():
    target = {"qb": 450, "tr": 270, "sab": 180}
    states = {"qb": S, "tr": K, "sab": S}
    speeds = {"qb": 450, "tr": 20, "sab": 180}
    out = apply_demand(target, states, speeds, {"qb": 50}, 45, True)
    assert out == approx_dict({"qb": 562.5, "tr": 45, "sab": 292.5})


# --- upload example: 80 Mbps, 50/50, safety net 4 ----------------------------

def test_upload_example_seeding_at_5():
    out = apply_demand({"a": 40, "b": 40}, {"a": S, "b": K}, {"a": 40, "b": 5}, {}, 4, True)
    assert out == approx_dict({"a": 72.5, "b": 7.5})


# --- guards ------------------------------------------------------------------

def test_disabled_returns_target_unchanged():
    out = apply_demand({"a": 450, "b": 450}, {"a": S, "b": K}, {"a": 450, "b": 40}, {}, 45, False)
    assert out == {"a": 450, "b": 450}


def test_no_saturated_client_returns_target_unchanged():
    out = apply_demand({"a": 450, "b": 450}, {"a": K, "b": K}, {"a": 40, "b": 40}, {}, 45, True)
    assert out == {"a": 450, "b": 450}


def test_unknown_clients_keep_target_and_do_not_count_as_saturated():
    out = apply_demand({"a": 450, "b": 450}, {"a": U, "b": K}, {"a": 450, "b": 40}, {}, 45, True)
    assert out == {"a": 450, "b": 450}


def test_inactive_clients_absent_from_states_keep_target():
    # Inactive client c is not classified; it keeps its safety-net target.
    out = apply_demand({"a": 427.5, "b": 427.5, "c": 45}, {"a": S, "b": K}, {"a": 427.5, "b": 40}, {}, 45, True)
    assert out == approx_dict({"a": 795, "b": 60, "c": 45})


def test_sum_is_preserved():
    target = {"qb": 450, "tr": 270, "sab": 180}
    out = apply_demand(target, {"qb": K, "tr": K, "sab": S}, {"qb": 100, "tr": 20, "sab": 180}, {}, 45, True)
    assert sum(out.values()) == pytest.approx(900.0)


def test_returns_a_new_dict():
    target = {"a": 450, "b": 450}
    out = apply_demand(target, {"a": S, "b": K}, {"a": 450, "b": 40}, {}, 45, True)
    assert out is not target and target == {"a": 450, "b": 450}
