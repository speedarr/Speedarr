"""Per-client-id throttle-decision writer helper."""
from app.services.polling_monitor import build_decision_per_client


def _stats(dl=None, ul=None, name="qB", ctype="qbittorrent"):
    return {"download_limit": dl, "upload_limit": ul, "client_name": name, "client_type": ctype}


def test_download_change_recorded_per_id():
    old = {"qbittorrent_1": _stats(dl=500), "sabnzbd_1": _stats(dl=200, name="SAB", ctype="sabnzbd")}
    new = {"qbittorrent_1": _stats(dl=100), "sabnzbd_1": _stats(dl=200, name="SAB", ctype="sabnzbd")}
    result = build_decision_per_client(old, new, "download")
    assert result == {
        "qbittorrent_1": {"name": "qB", "type": "qbittorrent",
                          "old_download_limit": 500, "new_download_limit": 100}
    }


def test_both_same_type_clients_captured():
    old = {"qbittorrent_1": _stats(dl=500), "qbittorrent_2": _stats(dl=300, name="qB2")}
    new = {"qbittorrent_1": _stats(dl=100), "qbittorrent_2": _stats(dl=80, name="qB2")}
    result = build_decision_per_client(old, new, "download")
    assert set(result) == {"qbittorrent_1", "qbittorrent_2"}
    assert result["qbittorrent_2"]["new_download_limit"] == 80


def test_no_change_returns_empty():
    old = {"qbittorrent_1": _stats(dl=100)}
    new = {"qbittorrent_1": _stats(dl=100)}
    assert build_decision_per_client(old, new, "download") == {}


def test_upload_direction_keys():
    old = {"qbittorrent_1": _stats(ul=50)}
    new = {"qbittorrent_1": _stats(ul=20)}
    assert build_decision_per_client(old, new, "upload") == {
        "qbittorrent_1": {"name": "qB", "type": "qbittorrent",
                          "old_upload_limit": 50, "new_upload_limit": 20}
    }


def test_missing_client_falls_back_to_id_name():
    old = {"deluge_9": {"download_limit": 70, "client_type": "deluge"}}
    new = {"deluge_9": {"download_limit": 10, "client_type": "deluge"}}
    result = build_decision_per_client(old, new, "download")
    assert result["deluge_9"]["name"] == "deluge_9"
