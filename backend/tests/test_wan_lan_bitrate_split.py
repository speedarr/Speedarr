"""WAN/LAN stream bitrate split for the dashboard status card."""
from app.utils.bandwidth import split_stream_bitrate_by_network


def test_all_wan():
    streams = [
        {"is_lan": False, "stream_bitrate_mbps": 10.0},
        {"is_lan": False, "stream_bitrate_mbps": 5.0},
    ]
    assert split_stream_bitrate_by_network(streams) == (15.0, 0.0)


def test_all_lan():
    streams = [{"is_lan": True, "stream_bitrate_mbps": 8.0}]
    assert split_stream_bitrate_by_network(streams) == (0.0, 8.0)


def test_mixed_wan_and_lan():
    streams = [
        {"is_lan": False, "stream_bitrate_mbps": 12.0},
        {"is_lan": True, "stream_bitrate_mbps": 3.0},
        {"is_lan": False, "stream_bitrate_mbps": 6.0},
    ]
    assert split_stream_bitrate_by_network(streams) == (18.0, 3.0)


def test_missing_is_lan_defaults_to_wan():
    streams = [{"stream_bitrate_mbps": 7.0}]
    assert split_stream_bitrate_by_network(streams) == (7.0, 0.0)


def test_missing_bitrate_counts_as_zero():
    streams = [{"is_lan": False}, {"is_lan": True}]
    assert split_stream_bitrate_by_network(streams) == (0.0, 0.0)


def test_empty():
    assert split_stream_bitrate_by_network([]) == (0.0, 0.0)
