"""Media-server resolution for connection testing (by id, not first-by-type)."""
from types import SimpleNamespace
from app.api.settings import resolve_test_media_server


def _s(sid, stype="plex", url="u", token="t"):
    return SimpleNamespace(id=sid, type=stype, url=url, token=token)


def test_resolves_by_id_when_supplied():
    servers = [_s("plex_1"), _s("plex_2")]
    assert resolve_test_media_server(servers, "plex", "plex_2").id == "plex_2"


def test_sole_server_of_type_when_no_id():
    servers = [_s("plex_1")]
    assert resolve_test_media_server(servers, "plex", None).id == "plex_1"


def test_ambiguous_type_without_id_returns_none():
    servers = [_s("plex_1"), _s("plex_2")]
    assert resolve_test_media_server(servers, "plex", None) is None


def test_unknown_id_returns_none():
    assert resolve_test_media_server([_s("plex_1")], "plex", "nope") is None
