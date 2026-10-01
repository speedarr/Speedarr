"""Test Connection sends a stored secret only to its stored address (audit T1-2).

Before: the masked placeholder (or use_existing) resolved the real secret from the store and the
request went to whatever URL the caller supplied, so a caller who can never read a secret could make
Speedarr deliver it to a host they name. ntfy already pinned to the saved server; SNMP refuses masked
secrets; Pushover, Telegram and Discord post to fixed hosts or carry the secret as the URL itself.
"""
from types import SimpleNamespace

import pytest

from app.api import settings
from app.config import (
    SpeedarrConfig, BandwidthConfig, DownloadBandwidthConfig, UploadBandwidthConfig,
    StreamBandwidthConfig, DownloadClientConfig, MediaServerConfig, REDACTED,
)

PIN = "to test a different address"
ATTACKER = "http://attacker.example"


def _config():
    cfg = SpeedarrConfig(bandwidth=BandwidthConfig(
        download=DownloadBandwidthConfig(total_limit=100.0),
        upload=UploadBandwidthConfig(total_limit=50.0),
        streams=StreamBandwidthConfig(),
    ))
    cfg.media_servers = [
        MediaServerConfig(id="plex_1", name="Plex", type="plex", url="http://plex:32400",
                          token="AUDITMARK-plex", api_key=""),
        MediaServerConfig(id="emby_1", name="Emby", type="emby", url="http://emby:8096",
                          token="", api_key="AUDITMARK-emby"),
    ]
    cfg.download_clients = [
        DownloadClientConfig(id="qb_1", type="qbittorrent", name="qb", url="http://qb:8080",
                             username="u", password="AUDITMARK-qb"),
        DownloadClientConfig(id="sab_1", type="sabnzbd", name="sab", url="http://sab:8080",
                             api_key="AUDITMARK-sab"),
        DownloadClientConfig(id="nzb_1", type="nzbget", name="nzb", url="http://nzb:6789",
                             username="u", password="AUDITMARK-nzb"),
        DownloadClientConfig(id="tr_1", type="transmission", name="tr", url="http://tr:9091",
                             username="u", password="AUDITMARK-tr"),
        DownloadClientConfig(id="de_1", type="deluge", name="de", url="http://de:8112",
                             password="AUDITMARK-de"),
    ]
    cfg.notifications.gotify.server_url = "http://gotify:80"
    cfg.notifications.gotify.app_token = "AUDITMARK-gotify"
    return cfg


class _Recorder:
    """Stands in for every client class: records how it was built, never connects."""
    built = []

    def __init__(self, *args, **kwargs):
        _Recorder.built.append((args, kwargs))

    async def test_connection(self):
        return True

    async def close(self):
        pass


@pytest.fixture(autouse=True)
def clients(monkeypatch):
    _Recorder.built = []
    for target in ("app.clients.plex.PlexClient", "app.clients.qbittorrent.QBittorrentClient",
                   "app.clients.sabnzbd.SABnzbdClient", "app.clients.nzbget.NZBGetClient",
                   "app.clients.transmission.TransmissionClient", "app.clients.deluge.DelugeClient"):
        monkeypatch.setattr(target, _Recorder)
    monkeypatch.setattr("app.clients.media_server_factory.create_media_server", lambda cfg: _Recorder(cfg))
    return _Recorder


async def _test(service, config, use_existing=False, app_config=None):
    state = SimpleNamespace(config=app_config or _config(), media_servers={})
    request = SimpleNamespace(app=SimpleNamespace(state=state))
    return await settings.test_connection(
        service, settings.TestConnectionRequest(config=config, use_existing=use_existing),
        request, SimpleNamespace(id=1))


def _built(entry, field):
    """(url, secret) the client was built with: kwargs for download clients, a config object for
    media servers."""
    args, kwargs = entry
    if kwargs:
        return kwargs["url"], kwargs[field]
    cfg = args[0]
    return cfg.url, getattr(cfg, field)


# service, saved id, saved url, secret field, secret name in the refusal
CASES = [
    ("plex", "plex_1", "http://plex:32400", "token", "token"),
    ("emby", "emby_1", "http://emby:8096", "api_key", "API key"),
    ("qbittorrent", "qb_1", "http://qb:8080", "password", "password"),
    ("sabnzbd", "sab_1", "http://sab:8080", "api_key", "API key"),
    ("nzbget", "nzb_1", "http://nzb:6789", "password", "password"),
    ("transmission", "tr_1", "http://tr:9091", "password", "password"),
    ("deluge", "de_1", "http://de:8112", "password", "password"),
]


@pytest.mark.parametrize("service,sid,saved_url,field,name", CASES)
async def test_a_masked_secret_never_travels_to_a_different_address(service, sid, saved_url, field, name, clients):
    resp = await _test(service, {"id": sid, "url": ATTACKER, field: REDACTED})
    assert resp.success is False and PIN in resp.message and name in resp.message
    assert clients.built == []


@pytest.mark.parametrize("service,sid,saved_url,field,name", CASES)
async def test_use_existing_is_pinned_the_same_way(service, sid, saved_url, field, name, clients):
    resp = await _test(service, {"id": sid, "url": ATTACKER, field: ""}, use_existing=True)
    assert resp.success is False and PIN in resp.message
    assert clients.built == []


@pytest.mark.parametrize("suffix", ["", "/"])
@pytest.mark.parametrize("service,sid,saved_url,field,name", CASES)
async def test_the_stored_address_goes_through_with_the_stored_secret(service, sid, saved_url, field, name, suffix, clients):
    resp = await _test(service, {"id": sid, "url": saved_url + suffix, field: REDACTED})
    assert resp.success is True, resp.message
    assert len(clients.built) == 1
    url, secret = _built(clients.built[0], field)
    assert url.rstrip("/") == saved_url
    assert secret.startswith("AUDITMARK-")


@pytest.mark.parametrize("service,sid,saved_url,field,name", CASES)
async def test_no_address_at_all_means_the_stored_one(service, sid, saved_url, field, name, clients):
    resp = await _test(service, {"id": sid, field: REDACTED})
    assert resp.success is True, resp.message
    url, secret = _built(clients.built[0], field)
    assert url == saved_url and secret.startswith("AUDITMARK-")


@pytest.mark.parametrize("service,sid,saved_url,field,name", CASES)
async def test_a_typed_secret_goes_wherever_the_caller_says(service, sid, saved_url, field, name, clients):
    resp = await _test(service, {"id": sid, "url": "http://elsewhere.example", field: "typed-secret"})
    assert resp.success is True, resp.message
    url, secret = _built(clients.built[0], field)
    assert url == "http://elsewhere.example" and secret == "typed-secret"


async def test_without_an_id_the_first_client_of_the_type_is_the_only_target(clients):
    # Review Focus 3: two qBittorrent clients, no id sent, the caller names the second's address.
    cfg = _config()
    cfg.download_clients.append(DownloadClientConfig(
        id="qb_2", type="qbittorrent", name="qb2", url="http://qb2:8080", username="u", password="AUDITMARK-qb2"))
    resp = await _test("qbittorrent", {"url": "http://qb2:8080", "password": REDACTED}, app_config=cfg)
    assert resp.success is False and PIN in resp.message
    assert clients.built == []
    resp = await _test("qbittorrent", {"url": "http://qb:8080", "password": REDACTED}, app_config=cfg)
    assert resp.success is True and _built(clients.built[0], "password")[1] == "AUDITMARK-qb"


class _Session:
    """aiohttp.ClientSession stand-in for the Gotify test: records posts, answers 200."""
    posted = []

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def post(self, url, **kwargs):
        _Session.posted.append((url, kwargs))
        return self

    status = 200

    async def text(self):
        return ""


async def test_gotify_masked_token_is_pinned_to_the_saved_server(monkeypatch):
    _Session.posted = []
    monkeypatch.setattr("aiohttp.ClientSession", _Session)
    resp = await _test("gotify", {"server_url": ATTACKER, "app_token": REDACTED})
    assert resp.success is False and PIN in resp.message and "app token" in resp.message
    assert _Session.posted == []
    resp = await _test("gotify", {"server_url": "http://gotify:80/", "app_token": REDACTED})
    assert resp.success is True, resp.message
    url, kwargs = _Session.posted[0]
    assert url == "http://gotify:80/message" and kwargs["headers"]["X-Gotify-Key"] == "AUDITMARK-gotify"
