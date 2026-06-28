"""Per-client decision reader helpers (per_client + legacy fallback)."""
from types import SimpleNamespace
from app.api.decisions import decision_client_map, has_limit_changes, build_decision_message


def _row(**kw):
    base = dict(
        per_client=None,
        qbittorrent_old_download_limit=None, qbittorrent_new_download_limit=None,
        qbittorrent_old_upload_limit=None, qbittorrent_new_upload_limit=None,
        sabnzbd_old_download_limit=None, sabnzbd_new_download_limit=None,
        decision_type="throttle", active_streams=0, reason=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def test_prefers_per_client_for_non_qb_sab_client():
    row = _row(per_client={"nzbget_9": {"name": "NZB", "type": "nzbget",
                                        "old_download_limit": 300, "new_download_limit": 50}})
    cm = decision_client_map(row)
    assert "nzbget_9" in cm
    assert has_limit_changes(cm) is True


def test_legacy_fallback_when_no_per_client():
    row = _row(qbittorrent_old_download_limit=500, qbittorrent_new_download_limit=100)
    cm = decision_client_map(row)
    assert cm["qbittorrent"]["new_download_limit"] == 100
    assert has_limit_changes(cm) is True


def test_no_change_not_flagged():
    row = _row(per_client={"qb_1": {"name": "qB", "type": "qbittorrent",
                                    "old_download_limit": 100, "new_download_limit": 100}})
    assert has_limit_changes(decision_client_map(row)) is False


def test_message_covers_all_clients():
    row = _row(per_client={
        "qb_1": {"name": "qB", "type": "qbittorrent", "old_download_limit": 500, "new_download_limit": 100},
        "nzb_1": {"name": "NZB", "type": "nzbget", "old_download_limit": 300, "new_download_limit": 80},
    })
    msg = build_decision_message(row.decision_type, decision_client_map(row), row.active_streams, row.reason)
    assert "qB download: 500 -> 100 Mbps" in msg
    assert "NZB download: 300 -> 80 Mbps" in msg
