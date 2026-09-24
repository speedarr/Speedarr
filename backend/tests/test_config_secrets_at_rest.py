"""Secrets are Fernet-encrypted at rest whatever row carries them, and history never holds one (audit T1-1)."""
import json
from types import SimpleNamespace

import pytest
from sqlalchemy import select, func

from app.models.configuration import Configuration, ConfigurationHistory
from app.services.config_manager import ConfigManager
from app.config import (
    SpeedarrConfig, BandwidthConfig, DownloadBandwidthConfig, UploadBandwidthConfig,
    StreamBandwidthConfig, decrypt_value, REDACTED,
)


def _base():
    return SpeedarrConfig(bandwidth=BandwidthConfig(
        download=DownloadBandwidthConfig(total_limit=100.0),
        upload=UploadBandwidthConfig(total_limit=50.0),
        streams=StreamBandwidthConfig(),
    ))


def _manager():
    state = SimpleNamespace(config=None, polling_monitor=None, decision_engine=None,
                            controller_manager=None, notification_service=None)
    return ConfigManager(app=SimpleNamespace(state=state))


async def _dump(db):
    """Every value in both tables as one string, for a 'no cleartext anywhere' assertion."""
    parts = [r.value for r in (await db.execute(select(Configuration))).scalars().all()]
    for h in (await db.execute(select(ConfigurationHistory))).scalars().all():
        parts += [h.old_value or "", h.new_value]
    return "\n".join(parts)


async def _row(db, key):
    return (await db.execute(select(Configuration).where(Configuration.key == key))).scalar_one_or_none()


async def _history(db, key):
    q = select(ConfigurationHistory).where(ConfigurationHistory.key == key).order_by(ConfigurationHistory.id)
    return (await db.execute(q)).scalars().all()


CLIENT = {"id": "qb_1", "type": "qbittorrent", "name": "qb", "url": "http://qb", "username": "u",
          "password": "AUDITMARK-qb-pass", "api_key": None, "enabled": True, "supports_upload": True,
          "max_speed_mbps": None, "color": "#3b82f6"}
SERVER = {"id": "plex_1", "name": "Plex", "type": "plex", "url": "http://plex", "token": "AUDITMARK-plex-token",
          "api_key": "", "enabled": True, "include_lan_streams": False, "lan_networks": []}


async def test_client_password_and_server_token_are_encrypted_leaf_level(db):
    # update_full_config() requires the _migrated sentinel (it's only ever called in production
    # after migrate_yaml_to_db has set it - see app/api/settings.py initialize-config).
    db.add(Configuration(key="_migrated", value="true", value_type="boolean"))
    await db.commit()
    cm = _manager()
    data = _base().model_dump()
    data["download_clients"] = [CLIENT]
    data["media_servers"] = [SERVER]
    await cm.update_full_config(data, db)

    assert "AUDITMARK" not in await _dump(db)
    row = await _row(db, "download_clients")
    assert row.value_type == "json"
    stored = json.loads(row.value)
    assert stored[0]["url"] == "http://qb"                        # non-secret leaves stay readable
    assert decrypt_value(stored[0]["password"]) == "AUDITMARK-qb-pass"
    servers = json.loads((await _row(db, "media_servers")).value)
    assert decrypt_value(servers[0]["token"]) == "AUDITMARK-plex-token"
    assert servers[0]["api_key"] == ""                             # empty means empty

    loaded = await cm.load_config_from_db(db)
    assert loaded.download_clients[0].password == "AUDITMARK-qb-pass"
    assert loaded.media_servers[0].token == "AUDITMARK-plex-token"
    assert loaded.media_servers[0].api_key == ""


async def test_history_holds_placeholders_not_ciphertext_for_secret_rows(db):
    # See the _migrated note in test_client_password_and_server_token_are_encrypted_leaf_level.
    db.add(Configuration(key="_migrated", value="true", value_type="boolean"))
    await db.commit()
    cm = _manager()
    data = _base().model_dump()
    data["download_clients"] = [CLIENT]
    await cm.update_full_config(data, db)
    data["download_clients"] = [dict(CLIENT, password="AUDITMARK-qb-pass-2")]
    await cm.update_full_config(data, db)

    first, second = await _history(db, "download_clients")
    assert first.old_value is None
    assert json.loads(first.new_value)[0]["password"] == REDACTED
    assert json.loads(second.old_value)[0]["password"] == REDACTED
    assert json.loads(second.new_value)[0]["password"] == REDACTED
    assert "gAAAA" not in (first.new_value + second.old_value + second.new_value)
    assert json.loads(second.new_value)[0]["url"] == "http://qb"   # non-secret history stays useful


async def test_the_four_t1_3_keys_are_encrypted_at_rest(db):
    cm = _manager()
    await cm.migrate_yaml_to_db(_base(), db)
    cm.app.state.config = await cm.load_config_from_db(db)
    await cm.update_section("snmp", {"enabled": False, "host": "router", "community": "AUDITMARK-snmp"}, db)
    await cm.update_section("notifications", {
        "pushover": {"enabled": False, "user_key": "AUDITMARK-pu", "api_token": "AUDITMARK-po"},
        "telegram": {"enabled": False, "bot_token": "AUDITMARK-bt", "chat_id": "AUDITMARK-chat"},
        "ntfy": {"enabled": False, "topic": "AUDITMARK-topic"},
    }, db)

    assert "AUDITMARK" not in await _dump(db)
    for key in ("snmp.community", "notifications.pushover.user_key",
                "notifications.telegram.chat_id", "notifications.ntfy.topic"):
        row = await _row(db, key)
        assert row.value_type == "string" and row.value.startswith("gAAAA"), key
        assert (await _history(db, key))[-1].new_value == REDACTED
    loaded = await cm.load_config_from_db(db)
    assert loaded.snmp.community == "AUDITMARK-snmp"
    assert loaded.notifications.telegram.chat_id == "AUDITMARK-chat"
    assert loaded.notifications.ntfy.topic == "AUDITMARK-topic"


async def test_yaml_import_protects_secrets(db):
    cm = _manager()
    cfg = _base()
    cfg.snmp.community = "AUDITMARK-import"
    await cm.migrate_yaml_to_db(cfg, db)
    assert "AUDITMARK" not in await _dump(db)
    assert (await cm.load_config_from_db(db)).snmp.community == "AUDITMARK-import"


@pytest.mark.parametrize("key", [
    "snmp.community",
    "notifications.pushover.user_key",
    "notifications.telegram.chat_id",
    "notifications.ntfy.topic",
    "plex.token",
])
async def test_placeholder_keeps_stored_ciphertext_byte_identical(db, key):
    cm = _manager()
    await cm._update_key(key, "AUDITMARK-value", db, None)
    await db.commit()
    before = (await _row(db, key)).value
    assert before.startswith("gAAAA")
    count = (await db.execute(select(func.count()).select_from(ConfigurationHistory))).scalar()
    await cm._update_key(key, REDACTED, db, None)
    await db.commit()
    assert (await _row(db, key)).value == before
    assert (await db.execute(select(func.count()).select_from(ConfigurationHistory))).scalar() == count


async def test_undecryptable_leaf_fails_fast_with_the_key_message(db):
    # A leaf that is not a Fernet token under this key (rotated CONFIG_ENCRYPTION_KEY, or a row that
    # skipped the migration) must raise the existing fail-fast error, never load as cleartext.
    db.add(Configuration(key="_migrated", value="true", value_type="boolean"))
    db.add(Configuration(key="download_clients", value=json.dumps([dict(CLIENT, password="not-a-fernet-token")]),
                         value_type="json"))
    await db.commit()
    with pytest.raises(ValueError, match="CONFIG_ENCRYPTION_KEY"):
        await _manager().load_config_from_db(db)


async def test_empty_list_and_none_secrets_round_trip(db):
    # See the _migrated note in test_client_password_and_server_token_are_encrypted_leaf_level.
    db.add(Configuration(key="_migrated", value="true", value_type="boolean"))
    await db.commit()
    cm = _manager()
    data = _base().model_dump()
    data["download_clients"] = [dict(CLIENT, password=None, api_key=None)]
    data["media_servers"] = []
    await cm.update_full_config(data, db)
    loaded = await cm.load_config_from_db(db)
    assert loaded.download_clients[0].password is None
    assert loaded.media_servers == []
