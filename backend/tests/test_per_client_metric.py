"""Per-client-id metric helpers for bandwidth recording."""
from app.services.polling_monitor import build_per_client_metrics, sum_stat_by_type


def _two_qbit():
    return {
        "qbittorrent_111": {
            "client_type": "qbittorrent",
            "download_speed": 142.0, "upload_speed": 68.0,
            "download_limit": 433.0, "upload_limit": 186.0,
        },
        "qbittorrent_222": {
            "client_type": "qbittorrent",
            "download_speed": 38.0, "upload_speed": 12.0,
            "download_limit": 100.0, "upload_limit": 50.0,
        },
    }


def test_build_per_client_keeps_both_same_type_clients():
    result = build_per_client_metrics(_two_qbit())
    assert set(result.keys()) == {"qbittorrent_111", "qbittorrent_222"}
    assert result["qbittorrent_111"] == {"d": 142.0, "u": 68.0, "dl": 433.0, "ul": 186.0}
    assert result["qbittorrent_222"] == {"d": 38.0, "u": 12.0, "dl": 100.0, "ul": 50.0}


def test_build_per_client_tolerates_missing_fields():
    stats = {"sab_1": {"client_type": "sabnzbd", "download_speed": 10.0}}
    assert build_per_client_metrics(stats) == {
        "sab_1": {"d": 10.0, "u": None, "dl": None, "ul": None}
    }


def test_sum_stat_by_type_sums_same_type():
    stats = _two_qbit()
    assert sum_stat_by_type(stats, "qbittorrent", "download_speed") == 180.0
    assert sum_stat_by_type(stats, "qbittorrent", "upload_speed") == 80.0
    assert sum_stat_by_type(stats, "qbittorrent", "download_limit") == 533.0


def test_sum_stat_by_type_returns_none_when_absent():
    stats = _two_qbit()
    assert sum_stat_by_type(stats, "deluge", "download_speed") is None


def test_sum_stat_by_type_ignores_none_values():
    stats = {
        "qb_1": {"client_type": "qbittorrent", "download_speed": 5.0},
        "qb_2": {"client_type": "qbittorrent", "download_speed": None},
    }
    assert sum_stat_by_type(stats, "qbittorrent", "download_speed") == 5.0
