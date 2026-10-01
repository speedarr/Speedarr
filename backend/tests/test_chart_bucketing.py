"""Chart data is averaged into the requested interval on the server; raw stays raw (audit B3-1).

Before: the handler returned every row in the window as ORM objects built on the event loop and
ignored interval_minutes, so "Last 3 Days" was ~52,000 rows per request.
"""
import json
from datetime import datetime, timedelta, timezone

from fastapi import Response

from app.api.bandwidth import build_chart_payload, CHART_COLUMNS, get_bandwidth_chart_data
from app.models import BandwidthMetric

NOW = datetime(2026, 9, 25, 12, 0, 0, tzinfo=timezone.utc)
T0 = datetime(2026, 9, 25, 10, 0, 0)          # naive UTC, as the column stores it


def _row(seconds, **fields):
    """A row mapping with every chart column, None unless given; per_client/per_server as JSON."""
    m = {c.key: None for c in CHART_COLUMNS}
    m["timestamp"] = T0 + timedelta(seconds=seconds)
    per_client = fields.pop("per_client", None)
    m["per_client"] = json.dumps(per_client) if per_client is not None else None
    per_server = fields.pop("per_server", None)
    m["per_server"] = json.dumps(per_server) if per_server is not None else None
    m.update(fields)
    return m


def _payload(rows, interval):
    return json.loads(build_chart_payload(rows, interval, NOW))


def test_raw_returns_every_row_and_keeps_none_limits():
    rows = [_row(0, per_client={"qb_1": {"d": 10, "u": 1, "dl": None, "ul": None}}),
            _row(5, per_client={"qb_1": {"d": 20, "u": 1, "dl": 50, "ul": 5}})]
    body = _payload(rows, 0)
    assert len(body["data"]) == 2
    assert body["data"][0]["qb_1_download_limit"] is None
    assert body["data"][1]["qb_1_download_limit"] == 50
    assert body["interval_minutes"] == 0
    assert body["start_time"] == "2026-09-25T10:00:00Z" and body["end_time"] == "2026-09-25T10:00:05Z"


def test_bucketed_means_follow_the_browsers_floor_rule():
    # Rows at 0, 5, 10 and 65 s: a one-minute interval gives buckets 10:00 and 10:01.
    rows = [_row(0, per_client={"qb_1": {"d": 10, "u": 0, "dl": 100, "ul": 0}}, active_streams_count=1),
            _row(5, per_client={"qb_1": {"d": 20, "u": 0, "dl": 100, "ul": 0}}, active_streams_count=1),
            _row(10, per_client={"qb_1": {"d": 30, "u": 0, "dl": 100, "ul": 0}}, active_streams_count=2),
            _row(65, per_client={"qb_1": {"d": 40, "u": 0, "dl": 200, "ul": 0}}, active_streams_count=2)]
    body = _payload(rows, 1)
    assert [p["timestamp"] for p in body["data"]] == ["2026-09-25T10:00:00Z", "2026-09-25T10:01:00Z"]
    first, second = body["data"]
    assert first["qb_1_speed"] == 20 and first["qb_1_download_limit"] == 100
    assert first["active_streams_count"] == 4 / 3
    assert second["qb_1_speed"] == 40 and second["qb_1_download_limit"] == 200
    assert body["interval_minutes"] == 1
    assert body["client_series"] == [{"id": "qb_1", "type": "qb"}]
    assert body["start_time"] == "2026-09-25T10:00:00Z" and body["end_time"] == "2026-09-25T10:01:00Z"


def test_a_series_missing_from_some_rows_counts_as_zero_like_the_browser():
    rows = [_row(0, per_client={"qb_1": {"d": 10, "u": 0, "dl": None, "ul": 0}}),
            _row(5, per_client={"qb_1": {"d": 10, "u": 0, "dl": 60, "ul": 0},
                                "sab_1": {"d": 30, "u": 0, "dl": 90, "ul": 0}})]
    body = _payload(rows, 1)
    point = body["data"][0]
    assert point["sab_1_speed"] == 15            # (0 + 30) / 2
    assert point["sab_1_download_limit"] == 45   # (0 + 90) / 2
    assert point["qb_1_download_limit"] == 30    # (None -> 0 + 60) / 2
    assert {s["id"] for s in body["client_series"]} == {"qb_1", "sab_1"}


def test_per_server_points_bucket_the_same_way():
    rows = [_row(0, per_server={"plex_1": 8.0}),
            _row(5, per_server={"plex_1": 12.0, "emby_1": 4.0}),
            _row(65, per_server={"plex_1": 6.0})]
    body = _payload(rows, 1)
    assert body["per_server_series"] == ["emby_1", "plex_1"]
    assert body["per_server_points"][0] == {"timestamp": "2026-09-25T10:00:00Z", "plex_1": 10.0, "emby_1": 2.0}
    assert body["per_server_points"][1] == {"timestamp": "2026-09-25T10:01:00Z", "plex_1": 6.0}
    raw = _payload(rows, 0)
    assert raw["per_server_points"][1] == {"timestamp": "2026-09-25T10:00:05Z", "plex_1": 12.0, "emby_1": 4.0}


def test_legacy_rows_fold_into_type_keyed_series_in_both_modes():
    rows = [_row(0, qbittorrent_download_speed=10, qbittorrent_download_limit=100),
            _row(5, qbittorrent_download_speed=30, qbittorrent_download_limit=100)]
    assert _payload(rows, 0)["data"][0]["qbittorrent_speed"] == 10
    assert _payload(rows, 1)["data"][0]["qbittorrent_speed"] == 20
    assert _payload(rows, 1)["client_series"] == [{"id": "qbittorrent", "type": "qbittorrent"}]


def test_an_interval_longer_than_the_window_gives_one_bucket():
    # Review Focus 5.
    rows = [_row(0, active_streams_count=1), _row(30, active_streams_count=3)]
    body = _payload(rows, 60)
    assert len(body["data"]) == 1 and body["data"][0]["active_streams_count"] == 2


def test_empty_window_returns_now_for_both_ends():
    body = _payload([], 5)
    assert body["data"] == [] and body["per_server_points"] == [] and body["client_series"] == []
    assert body["start_time"] == body["end_time"] == NOW.isoformat() + "Z"


async def test_handler_raises_a_sub_floor_interval_and_serves_prebuilt_bytes(db):
    t = datetime.now(timezone.utc).replace(tzinfo=None)
    db.add(BandwidthMetric(timestamp=t - timedelta(seconds=30),
                           per_client=json.dumps({"qb_1": {"d": 10, "u": 0, "dl": 50, "ul": 0}})))
    db.add(BandwidthMetric(timestamp=t - timedelta(seconds=20),
                           per_client=json.dumps({"qb_1": {"d": 30, "u": 0, "dl": 50, "ul": 0}})))
    await db.commit()

    resp = await get_bandwidth_chart_data(hours=1, interval_minutes=0.1, db=db)
    assert isinstance(resp, Response) and resp.media_type == "application/json"
    body = json.loads(resp.body)
    assert body["interval_minutes"] == 0.25          # the floor, 15 s
    assert 1 <= len(body["data"]) <= 2               # the two rows may straddle a 15 s boundary
    assert body["client_series"] == [{"id": "qb_1", "type": "qb"}]

    raw = json.loads((await get_bandwidth_chart_data(hours=1, interval_minutes=0, db=db)).body)
    assert len(raw["data"]) == 2 and raw["interval_minutes"] == 0
    five = json.loads((await get_bandwidth_chart_data(hours=1, interval_minutes=5, db=db)).body)
    assert len(five["data"]) == 1 and five["data"][0]["qb_1_speed"] == 20
