"""Media server config model + legacy migration (issues #47, #32)."""
from app.config import MediaServerConfig, SpeedarrConfig, PlexConfig
from tests.conftest import make_config


def test_media_server_config_defaults():
    cfg = MediaServerConfig(id="abc", name="My Plex", type="plex")
    assert cfg.enabled is True
    assert cfg.url == "" and cfg.token == "" and cfg.api_key == ""
    assert cfg.include_lan_streams is False


def test_legacy_plex_is_synthesized_when_no_media_servers():
    cfg = make_config()
    cfg.plex = PlexConfig(url="http://plex:32400", token="tok", include_lan_streams=True)
    servers = cfg.get_all_media_servers()
    assert len(servers) == 1
    s = servers[0]
    assert s.id == "plex" and s.type == "plex" and s.name == "Plex"
    assert s.url == "http://plex:32400" and s.token == "tok"
    assert s.include_lan_streams is True


def test_explicit_media_servers_take_precedence_no_duplicate_plex():
    cfg = make_config()
    cfg.plex = PlexConfig(url="http://plex:32400", token="tok")
    cfg.media_servers = [MediaServerConfig(id="plex", name="Plex", type="plex", url="http://new:32400", token="t2")]
    servers = cfg.get_all_media_servers()
    # legacy "plex" must NOT be appended again
    assert [s.id for s in servers] == ["plex"]
    assert servers[0].url == "http://new:32400"


def test_no_plex_url_yields_only_explicit_servers():
    cfg = make_config()  # plex defaults to url=""
    cfg.media_servers = [MediaServerConfig(id="e1", name="Emby", type="emby", url="http://emby:8096", api_key="k")]
    servers = cfg.get_all_media_servers()
    assert [s.id for s in servers] == ["e1"]


def test_get_enabled_filters_disabled():
    cfg = make_config()
    cfg.media_servers = [
        MediaServerConfig(id="a", name="A", type="plex", url="u", enabled=True),
        MediaServerConfig(id="b", name="B", type="emby", url="u", enabled=False),
    ]
    cfg.plex = PlexConfig()  # no legacy
    assert [s.id for s in cfg.get_enabled_media_servers()] == ["a"]


def test_failsafe_grace_default():
    cfg = make_config()
    assert cfg.failsafe.server_hold_grace_seconds == 300
