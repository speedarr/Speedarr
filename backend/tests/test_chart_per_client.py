"""Per-client-id chart serialization helpers."""
from app.api.bandwidth import parse_per_client, client_series_from_ids


def test_parse_per_client_reads_both_clients():
    raw = '{"qbittorrent_111": {"d": 142.0, "u": 68.0, "dl": 433.0, "ul": 186.0}, "qbittorrent_222": {"d": 38.0, "u": 12.0, "dl": null, "ul": null}}'
    parsed = parse_per_client(raw)
    assert set(parsed.keys()) == {"qbittorrent_111", "qbittorrent_222"}
    assert parsed["qbittorrent_111"]["d"] == 142.0
    assert parsed["qbittorrent_222"]["dl"] is None


def test_parse_per_client_tolerates_null_and_bad_json():
    assert parse_per_client(None) == {}
    assert parse_per_client("not json") == {}


def test_client_series_derives_type_from_id():
    series = client_series_from_ids({"qbittorrent_111", "qbittorrent_222", "sabnzbd"})
    assert series == [
        {"id": "qbittorrent_111", "type": "qbittorrent"},
        {"id": "qbittorrent_222", "type": "qbittorrent"},
        {"id": "sabnzbd", "type": "sabnzbd"},
    ]
