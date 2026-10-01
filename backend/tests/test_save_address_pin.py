"""A save never moves a stored secret to a new address (audit NEW-5, the save-side twin of T1-2).

Before: every save path kept the stored secret whenever the masked placeholder came back (or, for a
section save, when the secret was left out), whatever the entry's address now said. An API-key holder
could PUT {url: attacker, password: ***REDACTED***}; the next poll or Test Connection delivered it.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.api.settings import (
    DownloadClientsUpdateRequest, MediaServersUpdateRequest, update_download_clients, update_media_servers,
)
from app.config import (
    SpeedarrConfig, BandwidthConfig, DownloadBandwidthConfig, UploadBandwidthConfig, StreamBandwidthConfig,
    DownloadClientConfig, MediaServerConfig, path_to_str, REDACTED,
)
from app.models.configuration import Configuration
from app.services.config_manager import ConfigManager


def _bandwidth():
    return BandwidthConfig(
        download=DownloadBandwidthConfig(total_limit=100.0),
        upload=UploadBandwidthConfig(total_limit=50.0),
        streams=StreamBandwidthConfig(),
    )


# --- the list saves: PUT /download-clients and PUT /media-servers -------------------------------------

QB = {"id": "qb_1", "type": "qbittorrent", "name": "Seedbox", "url": "http://qb:8080", "username": "u",
      "password": "AUDITMARK-qb-pass"}
SAB = {"id": "sab_1", "type": "sabnzbd", "name": "Usenet", "url": "http://sab:8080",
       "api_key": "AUDITMARK-sab-key", "max_speed_mbps": 100.0}
PLEX = {"id": "plex_1", "name": "Plex", "type": "plex", "url": "http://plex:32400", "token": "AUDITMARK-plex-token"}
JELLY = {"id": "jf_1", "name": "Jellyfin", "type": "jellyfin", "url": "http://jf:8096",
         "api_key": "AUDITMARK-jf-key"}


class _ConfigManager:
    """Records what the handler would write; the database side is covered by the section tests below."""

    def __init__(self):
        self.written = None
        self.reloaded = []

    async def update_full_config(self, config_data, db, user_id=None):
        self.written = config_data
        return SpeedarrConfig(**config_data)

    async def _reload_services(self, section_name, config):
        self.reloaded.append(section_name)


def _request(cm):
    config = SpeedarrConfig(
        bandwidth=_bandwidth(),
        download_clients=[DownloadClientConfig(**QB), DownloadClientConfig(**SAB)],
        media_servers=[MediaServerConfig(**PLEX), MediaServerConfig(**JELLY)],
    )
    state = SimpleNamespace(config=config, config_manager=cm, controller_manager=None, polling_monitor=None)
    return SimpleNamespace(app=SimpleNamespace(state=state))


async def _put_clients(cm, clients):
    return await update_download_clients(
        DownloadClientsUpdateRequest(clients=clients), request=_request(cm), db=None,
        current_user=SimpleNamespace(id=1),
    )


async def _put_servers(cm, servers):
    return await update_media_servers(
        MediaServersUpdateRequest(servers=servers), request=_request(cm), db=None,
        current_user=SimpleNamespace(id=1),
    )


def _written(cm, key, entry_id):
    return next(e for e in cm.written[key] if e["id"] == entry_id)


@pytest.mark.parametrize("entry, field, label", [
    (QB, "password", "password"),
    (SAB, "api_key", "API key"),
])
async def test_masked_client_secret_with_a_new_url_is_refused(entry, field, label):
    cm = _ConfigManager()
    other = SAB if entry is QB else QB
    with pytest.raises(HTTPException) as exc:
        await _put_clients(cm, [{**entry, "url": "http://attacker:9599", field: REDACTED}, dict(other)])
    assert exc.value.status_code == 400
    assert exc.value.detail == f'Download client "{entry["name"]}": enter the {label} to change its address'
    assert cm.written is None


async def test_masked_client_secret_with_the_same_url_is_kept():
    cm = _ConfigManager()
    await _put_clients(cm, [{**QB, "url": "http://qb:8080/", "password": REDACTED}, dict(SAB)])
    assert _written(cm, "download_clients", "qb_1")["password"] == "AUDITMARK-qb-pass"


async def test_typed_client_secret_may_go_to_a_new_url():
    cm = _ConfigManager()
    await _put_clients(cm, [{**QB, "url": "http://new-qb:8080", "password": "typed"}, dict(SAB)])
    assert _written(cm, "download_clients", "qb_1")["password"] == "typed"


async def test_cleared_client_secret_may_go_to_a_new_url():
    cm = _ConfigManager()
    await _put_clients(cm, [{**QB, "url": "http://new-qb:8080", "password": ""}, dict(SAB)])
    assert _written(cm, "download_clients", "qb_1")["password"] == ""


async def test_a_duplicated_id_is_checked_entry_by_entry():
    cm = _ConfigManager()
    with pytest.raises(HTTPException) as exc:
        await _put_clients(cm, [{**QB, "password": REDACTED},
                                {**QB, "url": "http://attacker:9599", "password": REDACTED}])
    assert exc.value.status_code == 400 and cm.written is None


async def test_a_new_id_cannot_carry_a_stored_secret():
    cm = _ConfigManager()
    await _put_clients(cm, [{**QB, "id": "qb_new", "url": "http://attacker:9599", "password": REDACTED}])
    assert _written(cm, "download_clients", "qb_new")["password"] is None


@pytest.mark.parametrize("entry, field, label", [
    (PLEX, "token", "token"),
    (JELLY, "api_key", "API key"),
])
async def test_masked_server_secret_with_a_new_url_is_refused(entry, field, label):
    cm = _ConfigManager()
    other = JELLY if entry is PLEX else PLEX
    with pytest.raises(HTTPException) as exc:
        await _put_servers(cm, [{**entry, "url": "http://attacker:9599", field: REDACTED}, dict(other)])
    assert exc.value.status_code == 400
    assert exc.value.detail == f'Media server "{entry["name"]}": enter the {label} to change its address'
    assert cm.written is None and cm.reloaded == []


async def test_masked_server_secret_with_the_same_url_is_kept():
    cm = _ConfigManager()
    await _put_servers(cm, [{**PLEX, "token": REDACTED}, {**JELLY, "url": "http://jf:8096/", "api_key": REDACTED}])
    assert _written(cm, "media_servers", "plex_1")["token"] == "AUDITMARK-plex-token"
    assert _written(cm, "media_servers", "jf_1")["api_key"] == "AUDITMARK-jf-key"


async def test_typed_server_secret_may_go_to_a_new_url():
    cm = _ConfigManager()
    await _put_servers(cm, [{**PLEX, "url": "http://new-plex:32400", "token": "typed"}, dict(JELLY)])
    assert _written(cm, "media_servers", "plex_1")["token"] == "typed"


async def test_a_new_server_id_cannot_carry_a_stored_secret():
    cm = _ConfigManager()
    await _put_servers(cm, [{**PLEX, "id": "plex_new", "url": "http://attacker:9599", "token": REDACTED}])
    assert _written(cm, "media_servers", "plex_new")["token"] == ""


# --- the section save: PUT /section/{name} -------------------------------------------------------------

@pytest.fixture
async def cm(db):
    state = SimpleNamespace(config=None, polling_monitor=None, decision_engine=None,
                            controller_manager=None, notification_service=None)
    manager = ConfigManager(app=SimpleNamespace(state=state))
    await manager.migrate_yaml_to_db(SpeedarrConfig(bandwidth=_bandwidth()), db)
    state.config = await manager.load_config_from_db(db)
    manager._reload_services = AsyncMock()
    await manager.update_section("notifications", {
        "gotify": {"server_url": "http://gotify", "app_token": "AUDITMARK-gotify"},
        "ntfy": {"server_url": "https://ntfy.example", "topic": "AUDITMARK-topic"},
    }, db)
    await manager.update_section("snmp", {"host": "router", "port": 161, "community": "AUDITMARK-snmp"}, db)
    return manager


async def _rows(db):
    return {r.key: r.value for r in (await db.execute(select(Configuration))).scalars().all()}


@pytest.mark.parametrize("section, payload, message", [
    ("notifications", {"gotify": {"server_url": "http://attacker:9599", "app_token": REDACTED}},
     "Gotify: enter the app token to change the server URL"),
    ("notifications", {"gotify": {"server_url": "http://attacker:9599"}},
     "Gotify: enter the app token to change the server URL"),
    ("notifications", {"ntfy": {"server_url": "http://attacker:9599", "topic": REDACTED}},
     "ntfy: enter the topic to change the server URL"),
    ("notifications", {"ntfy": {"server_url": "http://attacker:9599"}},
     "ntfy: enter the topic to change the server URL"),
    ("snmp", {"host": "attacker", "community": REDACTED},
     "SNMP: enter the community string to change the host"),
    ("snmp", {"port": 1161}, "SNMP: enter the community string to change the port"),
])
async def test_section_secret_kept_beside_a_new_address_is_refused(cm, db, section, payload, message):
    before = await _rows(db)
    with pytest.raises(ValueError) as exc:
        await cm.update_section(section, payload, db)
    assert str(exc.value) == message
    assert await _rows(db) == before


@pytest.mark.parametrize("section, payload", [
    ("notifications", {"gotify": {"server_url": "http://gotify/", "app_token": REDACTED, "enabled": True}}),
    ("notifications", {"gotify": {"server_url": "http://new-gotify", "app_token": "typed"}}),
    ("notifications", {"ntfy": {"server_url": "http://new-ntfy", "topic": ""}}),
    ("snmp", {"enabled": True, "community": REDACTED}),
    ("snmp", {"host": "new-router", "community": "typed"}),
])
async def test_section_save_without_a_moved_secret_goes_through(cm, db, section, payload):
    await cm.update_section(section, payload, db)


async def test_first_snmp_setup_from_an_empty_host_needs_the_community(db):
    state = SimpleNamespace(config=None, polling_monitor=None, decision_engine=None,
                            controller_manager=None, notification_service=None)
    manager = ConfigManager(app=SimpleNamespace(state=state))
    await manager.migrate_yaml_to_db(SpeedarrConfig(bandwidth=_bandwidth()), db)
    state.config = await manager.load_config_from_db(db)
    manager._reload_services = AsyncMock()
    with pytest.raises(ValueError, match="enter the community string to change the host"):
        await manager.update_section("snmp", {"enabled": True, "host": "router", "community": REDACTED}, db)
    cfg = await manager.update_section("snmp", {"enabled": True, "host": "router", "community": "public"}, db)
    assert cfg.snmp.host == "router"


async def test_the_legacy_plex_section_is_pinned_too(cm, db):
    # (qbittorrent/sabnzbd are None until written, and a first write to them fails on reload for
    # an unrelated reason - see the audit-fix ledger - so plex stands for the legacy sections)
    await cm.update_section("plex", {"url": "http://plex:32400", "token": "AUDITMARK-plex"}, db)
    with pytest.raises(ValueError) as exc:
        await cm.update_section("plex", {"url": "http://attacker:9599", "token": REDACTED}, db)
    assert str(exc.value) == "Plex: enter the token to change the URL"


async def test_an_empty_stored_secret_does_not_pin_the_address(cm, db):
    await cm.update_section("notifications", {"gotify": {"app_token": ""}}, db)
    cfg = await cm.update_section("notifications", {"gotify": {"server_url": "http://new-gotify"}}, db)
    assert cfg.notifications.gotify.server_url == "http://new-gotify"


# --- the registry ---------------------------------------------------------------------------------------

def test_address_registry_is_exactly_these_fields():
    from app.config import ADDRESS_PATHS

    assert {path_to_str(p) for p in ADDRESS_PATHS} == {
        "plex.url", "media_servers[].url", "qbittorrent.url", "sabnzbd.url", "download_clients[].url",
        "snmp.host", "snmp.port", "notifications.gotify.server_url", "notifications.ntfy.server_url",
    }
