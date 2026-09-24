"""encrypt_stored_secrets: rows already stored in clear are encrypted and history is scrubbed, once (audit T1-1).

The seed reproduces the audit instance's database: wizard defaults, then the cleartext rows T1-1 and
T1-3 found, next to rows that were already encrypted and history markers that must survive untouched.
"""
import inspect
import json
import logging
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.models.configuration import Configuration, ConfigurationHistory
from app.services.config_manager import ConfigManager, SECRETS_MARKER_KEY
from app.config import (
    SpeedarrConfig, BandwidthConfig, DownloadBandwidthConfig, UploadBandwidthConfig,
    StreamBandwidthConfig, encrypt_value, decrypt_value, REDACTED, SECRETS_SCHEMA_VERSION,
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


CLEAR_CLIENTS = json.dumps([{"id": "qb_1", "type": "qbittorrent", "name": "qb", "url": "http://qb",
                             "username": "u", "password": "AUDITMARK-qb", "enabled": True, "supports_upload": True}])
CLEAR_SERVERS = json.dumps([{"id": "p1", "name": "Plex", "type": "plex", "url": "http://plex",
                             "token": "AUDITMARK-plex", "api_key": "", "enabled": True}])


async def _put(db, key, value, value_type):
    row = (await db.execute(select(Configuration).where(Configuration.key == key))).scalar_one_or_none()
    if row:
        row.value, row.value_type = value, value_type
    else:
        db.add(Configuration(key=key, value=value, value_type=value_type))


async def _seed_audit_shape(db):
    cm = _manager()
    await cm.migrate_yaml_to_db(_base(), db)                  # _migrated + every default row
    await _put(db, "download_clients", CLEAR_CLIENTS, "json")
    await _put(db, "media_servers", CLEAR_SERVERS, "json")
    await _put(db, "snmp.community", "AUDITMARK-snmp", "string")
    await _put(db, "notifications.pushover.user_key", "AUDITMARK-pu", "string")
    await _put(db, "notifications.discord.webhook_url", encrypt_value("AUDITMARK-dc"), "string")  # already encrypted
    await _put(db, "plex.token", encrypt_value("AUDITMARK-plex-legacy"), "string")                 # legacy scalar
    db.add_all([
        ConfigurationHistory(key="download_clients", old_value=None, new_value=CLEAR_CLIENTS, value_type="json"),
        ConfigurationHistory(key="download_clients", old_value=CLEAR_CLIENTS, new_value="[DELETED]", value_type="json"),
        ConfigurationHistory(key="snmp.community", old_value="public", new_value="AUDITMARK-snmp", value_type="string"),
        ConfigurationHistory(key="plex.token", old_value=None, new_value=encrypt_value("AUDITMARK-plex-legacy"),
                             value_type="string"),
        ConfigurationHistory(key="snmp.host", old_value="a", new_value="router", value_type="string"),
    ])
    await db.commit()
    return cm


async def _rows(db):
    return {r.key: (r.value, r.value_type) for r in (await db.execute(select(Configuration))).scalars().all()}


async def _history(db):
    q = select(ConfigurationHistory).order_by(ConfigurationHistory.id)
    return [(h.key, h.old_value, h.new_value) for h in (await db.execute(q)).scalars().all()]


async def _dump(db):
    parts = [r.value for r in (await db.execute(select(Configuration))).scalars().all()]
    for h in (await db.execute(select(ConfigurationHistory))).scalars().all():
        parts += [h.old_value or "", h.new_value]
    return "\n".join(parts)


async def test_migration_encrypts_clear_rows_and_scrubs_history(db, caplog):
    cm = await _seed_audit_shape(db)
    before = await _rows(db)

    with caplog.at_level(logging.INFO, logger="app.services.config_manager"):
        changed = await cm.encrypt_stored_secrets(db)

    assert changed is True
    assert "AUDITMARK" not in await _dump(db)
    rows = await _rows(db)
    clients = json.loads(rows["download_clients"][0])
    assert decrypt_value(clients[0]["password"]) == "AUDITMARK-qb" and clients[0]["url"] == "http://qb"
    assert rows["download_clients"][1] == "json"
    servers = json.loads(rows["media_servers"][0])
    assert decrypt_value(servers[0]["token"]) == "AUDITMARK-plex" and servers[0]["api_key"] == ""
    assert decrypt_value(rows["snmp.community"][0]) == "AUDITMARK-snmp"
    assert decrypt_value(rows["notifications.pushover.user_key"][0]) == "AUDITMARK-pu"
    assert rows["notifications.discord.webhook_url"] == before["notifications.discord.webhook_url"]  # byte-identical
    assert rows["plex.token"] == before["plex.token"]
    assert rows[SECRETS_MARKER_KEY] == (str(SECRETS_SCHEMA_VERSION), "integer")

    hist = await _history(db)
    assert hist[0][1] is None and json.loads(hist[0][2])[0]["password"] == REDACTED
    assert json.loads(hist[1][1])[0]["password"] == REDACTED and hist[1][2] == "[DELETED]"
    assert hist[2][1:] == (REDACTED, REDACTED)
    assert hist[3][2] == REDACTED
    assert hist[4][1:] == ("a", "router")

    messages = [r.getMessage() for r in caplog.records]
    assert any("Encrypted stored secrets: 4 configuration rows updated, 4 history entries scrubbed" in m
               for m in messages), messages

    loaded = await cm.load_config_from_db(db)
    assert loaded.download_clients[0].password == "AUDITMARK-qb"
    assert loaded.snmp.community == "AUDITMARK-snmp"
    assert loaded.notifications.discord.webhook_url == "AUDITMARK-dc"


async def test_second_run_is_a_no_op(db):
    cm = await _seed_audit_shape(db)
    await cm.encrypt_stored_secrets(db)
    rows, hist = await _rows(db), await _history(db)
    assert await cm.encrypt_stored_secrets(db) is False
    assert await _rows(db) == rows
    assert await _history(db) == hist


async def test_half_done_run_heals_without_double_encrypting(db):
    cm = await _seed_audit_shape(db)
    already = json.dumps([dict(json.loads(CLEAR_CLIENTS)[0], password=encrypt_value("AUDITMARK-qb"))])
    await _put(db, "download_clients", already, "json")     # one row done, marker absent (crash mid-run)
    await db.commit()
    assert await cm.encrypt_stored_secrets(db) is True
    rows = await _rows(db)
    assert rows["download_clients"][0] == already            # untouched, not re-encrypted
    assert decrypt_value(rows["snmp.community"][0]) == "AUDITMARK-snmp"


async def test_marker_present_means_hands_off(db):
    # With the marker in place a rotated key must never get rows double-encrypted; the loader's
    # fail-fast error is the right outcome for that database.
    cm = await _seed_audit_shape(db)
    db.add(Configuration(key=SECRETS_MARKER_KEY, value=str(SECRETS_SCHEMA_VERSION), value_type="integer"))
    await db.commit()
    before = await _rows(db)
    assert await cm.encrypt_stored_secrets(db) is False
    assert await _rows(db) == before


async def test_lower_marker_version_reruns(db):
    cm = await _seed_audit_shape(db)
    db.add(Configuration(key=SECRETS_MARKER_KEY, value="0", value_type="integer"))
    await db.commit()
    assert await cm.encrypt_stored_secrets(db) is True
    assert (await _rows(db))[SECRETS_MARKER_KEY][0] == str(SECRETS_SCHEMA_VERSION)
    assert "AUDITMARK" not in await _dump(db)


async def test_empty_database_gets_the_marker_and_stays_in_setup_mode(db):
    cm = _manager()
    assert await cm.encrypt_stored_secrets(db) is True
    assert (await _rows(db))[SECRETS_MARKER_KEY][0] == str(SECRETS_SCHEMA_VERSION)
    assert await cm.load_config_from_db(db) is None


def test_startup_runs_the_migration_before_the_first_config_load():
    from app import main
    src = inspect.getsource(main.lifespan)
    assert src.index("encrypt_stored_secrets") < src.index("load_config_from_db")


async def test_rotated_key_aborts_the_migration_without_writing(db):
    # A token written under another key must stop the run cold: no row touched, no marker, the
    # key-changed message the operator already knows from the loader.
    from cryptography.fernet import Fernet
    cm = await _seed_audit_shape(db)
    foreign = Fernet(Fernet.generate_key()).encrypt(b"AUDITMARK-old").decode()
    await _put(db, "plex.token", foreign, "string")
    await db.commit()
    before, hist = await _rows(db), await _history(db)
    with pytest.raises(ValueError, match="CONFIG_ENCRYPTION_KEY"):
        await cm.encrypt_stored_secrets(db)
    assert await _rows(db) == before
    assert await _history(db) == hist
    assert SECRETS_MARKER_KEY not in await _rows(db)
