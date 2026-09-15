"""Pure demand-allocation helpers (#85)."""
import pytest

from app.services.demand_allocation import split_weights


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
