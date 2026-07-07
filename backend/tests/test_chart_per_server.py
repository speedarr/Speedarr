"""Pivot BandwidthMetric.per_server JSON into chart series."""
from app.api.bandwidth import pivot_per_server


def test_pivot_builds_series_and_points():
    rows = [
        ("2026-06-27T00:00:00", '{"a": 5.0, "b": 2.0}'),
        ("2026-06-27T00:00:05", '{"a": 6.0}'),
    ]
    series_ids, points = pivot_per_server(rows)
    assert set(series_ids) == {"a", "b"}
    assert points[0]["a"] == 5.0 and points[0]["b"] == 2.0
    assert points[1]["a"] == 6.0 and points[1].get("b", 0) == 0


def test_pivot_handles_null_and_bad_json():
    rows = [("t1", None), ("t2", "not json")]
    series_ids, points = pivot_per_server(rows)
    assert series_ids == []
    assert points == [{"timestamp": "t1"}, {"timestamp": "t2"}]
