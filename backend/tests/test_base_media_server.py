"""BaseMediaServer ABC + _finalize_stream helper."""
import pytest
from app.clients.base_media_server import BaseMediaServer
from app.config import MediaServerConfig


class _Dummy(BaseMediaServer):
    type = "plex"
    async def test_connection(self) -> bool:
        return True
    async def get_active_streams(self):
        return []


def _make(**kw):
    base = dict(id="srv1", name="Living Room", type="plex", url="http://x:32400/")
    base.update(kw)
    return _Dummy(MediaServerConfig(**base))


def test_init_strips_trailing_slash_and_copies_fields():
    s = _make(include_lan_streams=True)
    assert s.server_id == "srv1"
    assert s.name == "Living Room"
    assert s.url == "http://x:32400"  # trailing slash removed
    assert s.include_lan_streams is True


def test_finalize_stream_injects_attribution_and_prefixes_session_id():
    s = _make()
    out = s._finalize_stream({"media_type": "movie"}, raw_session_id="42")
    assert out["server_id"] == "srv1"
    assert out["server_name"] == "Living Room"
    assert out["server_type"] == "plex"
    assert out["session_id"] == "srv1:42"
    assert out["media_type"] == "movie"


def test_cannot_instantiate_abstract():
    with pytest.raises(TypeError):
        BaseMediaServer(MediaServerConfig(id="x", name="x", type="plex"))
