"""Per-server bandwidth aggregation helper."""
from app.services.polling_monitor import aggregate_per_server_bandwidth


def test_aggregates_by_server_id():
    streams = [
        {"server_id": "a", "stream_bitrate_mbps": 5.0},
        {"server_id": "a", "stream_bitrate_mbps": 3.0},
        {"server_id": "b", "stream_bitrate_mbps": 10.0},
    ]
    assert aggregate_per_server_bandwidth(streams) == {"a": 8.0, "b": 10.0}


def test_ignores_streams_without_server_id():
    assert aggregate_per_server_bandwidth([{"stream_bitrate_mbps": 5.0}]) == {}


def test_empty():
    assert aggregate_per_server_bandwidth([]) == {}
