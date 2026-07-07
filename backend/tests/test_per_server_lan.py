"""Per-server LAN inclusion policy."""
from app.utils.bandwidth import filter_streams_for_bandwidth


def test_wan_always_included():
    streams = [{"is_lan": False, "include_lan_streams": False}]
    assert len(filter_streams_for_bandwidth(streams)) == 1


def test_lan_excluded_when_server_policy_off():
    streams = [{"is_lan": True, "include_lan_streams": False}]
    assert filter_streams_for_bandwidth(streams) == []


def test_lan_included_when_server_policy_on():
    streams = [{"is_lan": True, "include_lan_streams": True}]
    assert len(filter_streams_for_bandwidth(streams)) == 1


def test_missing_policy_defaults_to_exclude_lan():
    streams = [{"is_lan": True}]
    assert filter_streams_for_bandwidth(streams) == []


def test_mixed_servers_independent_policy():
    streams = [
        {"is_lan": True, "include_lan_streams": True, "server_id": "a"},
        {"is_lan": True, "include_lan_streams": False, "server_id": "b"},
        {"is_lan": False, "include_lan_streams": False, "server_id": "b"},
    ]
    kept = filter_streams_for_bandwidth(streams)
    assert len(kept) == 2  # a's LAN (policy on) + b's WAN
