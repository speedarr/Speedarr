"""heal_stored_config repairs stored rows that stop the configuration loading (audit NEW-2).

Before: a database left unloadable (a rejected save under T2-1, a half-written legacy section, a value a
newer model refuses) started the app in setup mode with no throttling, and no API call could repair it:
every save reloads through the same rows. The heal runs at startup, resets only the failing settings to
their defaults, records each in history, and changes nothing unless the result loads.
"""
import json
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.config import (
    SpeedarrConfig, BandwidthConfig, DownloadBandwidthConfig, UploadBandwidthConfig, StreamBandwidthConfig,
    SystemConfig, DownloadClientConfig, MediaServerConfig, REDACTED, encrypt_value, looks_like_fernet_token,
)
from app.database import Base
from app.models.configuration import Configuration, ConfigurationHistory
from app.services.config_manager import ConfigManager


@pytest.fixture
async def db():
    """Like conftest's db but autoflush=False, as production's AsyncSessionLocal (database.py)."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False, autoflush=False)
    async with Session() as session:
        yield session
    await engine.dispose()


def _base(**extra):
    return SpeedarrConfig(bandwidth=BandwidthConfig(
        download=DownloadBandwidthConfig(total_limit=100.0),
        upload=UploadBandwidthConfig(total_limit=50.0),
        streams=StreamBandwidthConfig(),
    ), **extra)


def _clients():
    return [
        DownloadClientConfig(id=f"qb_{i}", type="qbittorrent", name=f"QB {i}", url=f"http://qb{i}:8080",
                             username="admin", password=f"AUDITMARK-qb{i}", supports_upload=True)
        for i in range(3)
    ]


def _manager():
    state = SimpleNamespace(config=None, polling_monitor=None, decision_engine=None,
                            controller_manager=None, notification_service=None)
    return ConfigManager(app=SimpleNamespace(state=state))


@pytest.fixture
async def cm(db):
    manager = _manager()
    await manager.migrate_yaml_to_db(_base(), db)
    return manager


async def _row(db, key):
    return (await db.execute(select(Configuration).where(Configuration.key == key))).scalar_one_or_none()


async def _seed(db, key, value, value_type="string"):
    row = await _row(db, key)
    if row is None:
        db.add(Configuration(key=key, value=str(value), value_type=value_type))
    else:
        row.value, row.value_type = str(value), value_type
    await db.commit()


async def _drop(db, key):
    row = await _row(db, key)
    await db.delete(row)
    await db.commit()


async def _rows(db):
    return {r.key: (r.value, r.value_type) for r in (await db.execute(select(Configuration))).scalars().all()}


async def _history(db, key=None):
    q = select(ConfigurationHistory).order_by(ConfigurationHistory.id)
    if key is not None:
        q = q.where(ConfigurationHistory.key == key)
    return (await db.execute(q)).scalars().all()


async def _history_count(db):
    return (await db.execute(select(func.count()).select_from(ConfigurationHistory))).scalar()


def _warnings(lines):
    return [m for level, m in lines if level == "WARNING"]


# --- nothing to heal ------------------------------------------------------------------------------

async def test_a_clean_database_is_not_changed(cm, db):
    before, history = await _rows(db), await _history_count(db)
    assert await cm.heal_stored_config(db) == 0
    assert await _rows(db) == before
    assert await _history_count(db) == history


async def test_a_database_that_was_never_migrated_is_not_read(db):
    db.add(Configuration(key="system.log_level", value="LOUD", value_type="string"))
    await db.commit()
    assert await _manager().heal_stored_config(db) == 0
    assert (await _row(db, "system.log_level")).value == "LOUD"


async def test_a_complete_legacy_section_is_left_alone(db):
    # Review Focus 1: an old install still on the single-client section.
    manager = _manager()
    await manager.migrate_yaml_to_db(_base(qbittorrent={"url": "http://qb:8080", "username": "a", "password": "p"}), db)
    before = await _rows(db)
    assert await manager.heal_stored_config(db) == 0
    assert await _rows(db) == before


# --- scalar rows ----------------------------------------------------------------------------------

async def test_a_rejected_value_goes_back_to_its_default(cm, db, loguru_lines):
    await _seed(db, "system.log_level", "LOUD")
    assert await cm.load_config_from_db(db) is None

    assert await cm.heal_stored_config(db) == 1

    assert await _row(db, "system.log_level") is None
    loaded = await cm.load_config_from_db(db)
    assert loaded.system.log_level == SystemConfig().log_level
    last = (await _history(db, "system.log_level"))[-1]
    assert (last.old_value, last.new_value, last.changed_by) == ("LOUD", "[DELETED]", None)
    warnings = _warnings(loguru_lines)
    assert any(w.startswith("Healed config system.log_level: ") and w.endswith("; it now uses its default (audit NEW-2)") for w in warnings), warnings
    assert "Healed 1 stored settings that stopped the configuration loading; they now use their defaults (audit NEW-2)" in warnings


async def test_a_second_heal_finds_nothing(cm, db):
    await _seed(db, "system.log_level", "LOUD")
    assert await cm.heal_stored_config(db) == 1
    assert await cm.heal_stored_config(db) == 0


async def test_internal_rows_survive_a_heal(cm, db):
    # Review Focus 3.
    await _seed(db, "_client_baselines", json.dumps({"qb_1": {"download_limit": 5}}), "json")
    internal = {k: v for k, v in (await _rows(db)).items() if k.startswith("_")}
    await _seed(db, "system.log_level", "LOUD")
    assert await cm.heal_stored_config(db) == 1
    assert {k: v for k, v in (await _rows(db)).items() if k.startswith("_")} == internal


async def test_a_half_written_legacy_section_is_dropped(cm, db):
    await _drop(db, "qbittorrent")                       # the stored None row migrate_yaml_to_db wrote
    await _seed(db, "qbittorrent.url", "http://qb:8080")
    assert await cm.load_config_from_db(db) is None

    assert await cm.heal_stored_config(db) == 1

    assert [k for k in await _rows(db) if k.startswith("qbittorrent")] == []
    loaded = await cm.load_config_from_db(db)
    assert loaded.qbittorrent is None


async def test_dropped_legacy_secret_is_masked_in_history(cm, db, loguru_lines):
    # Review Focus 2.
    await _drop(db, "qbittorrent")
    await _seed(db, "qbittorrent.url", "http://qb:8080")
    await _seed(db, "qbittorrent.password", encrypt_value("AUDITMARK-legacy"))
    assert await cm.heal_stored_config(db) == 1
    last = (await _history(db, "qbittorrent.password"))[-1]
    assert (last.old_value, last.new_value) == (REDACTED, "[DELETED]")
    dump = "\n".join(m for _, m in loguru_lines) + "".join(h.old_value or "" for h in await _history(db))
    assert "AUDITMARK" not in dump and "gAAAA" not in dump


async def test_new7_shape_none_row_beside_children(cm, db, loguru_lines):
    # The NEW-7 write: child rows beside the stored None row; unflatten_dict raises on it.
    await _seed(db, "qbittorrent.url", "http://qb:8080")
    with pytest.raises(TypeError):
        await cm.load_config_from_db(db)

    assert await cm.heal_stored_config(db) == 2          # pass 0 + the legacy section

    assert [k for k in await _rows(db) if k.startswith("qbittorrent")] == []
    assert (await cm.load_config_from_db(db)).qbittorrent is None
    assert "Healed config qbittorrent: stored unset beside 1 settings under it; kept those (audit NEW-2)" in _warnings(loguru_lines)


async def test_rows_under_a_value_are_removed(cm, db, loguru_lines):
    await _seed(db, "bandwidth.download.client_percents.qb_1", 60, "integer")
    await _seed(db, "bandwidth.download.client_percents.qb_1.x", 1, "integer")

    assert await cm.heal_stored_config(db) == 1

    assert await _row(db, "bandwidth.download.client_percents.qb_1.x") is None
    # The loader's in-memory normalisation drops ids with no configured client, so check the stored row.
    assert (await _row(db, "bandwidth.download.client_percents.qb_1")).value == "60"
    assert await cm.load_config_from_db(db) is not None
    assert "Healed config bandwidth.download.client_percents.qb_1: 1 settings stored under a value; removed them (audit NEW-2)" in _warnings(loguru_lines)


async def test_a_dotted_client_id_percent_is_removed(cm, db):
    # T2-13's stored shape: the id "a.b" splits into a nested dict where an int is expected.
    await _seed(db, "bandwidth.download.client_percents.a.b", 30, "integer")
    await _seed(db, "bandwidth.download.client_percents.qb_1", 70, "integer")
    assert await cm.load_config_from_db(db) is None

    assert await cm.heal_stored_config(db) == 1

    assert await _row(db, "bandwidth.download.client_percents.a.b") is None
    assert (await _row(db, "bandwidth.download.client_percents.qb_1")).value == "70"
    assert await cm.load_config_from_db(db) is not None


async def test_several_faults_are_healed_in_one_run(cm, db):
    await _seed(db, "system.log_level", "LOUD")
    await _drop(db, "qbittorrent")
    await _seed(db, "qbittorrent.url", "http://qb:8080")
    await _seed(db, "bandwidth.download.client_percents.a.b", 30, "integer")

    assert await cm.heal_stored_config(db) == 3

    assert await cm.load_config_from_db(db) is not None
    assert await _row(db, "system.log_level") is None
    assert await _row(db, "qbittorrent.url") is None
    assert await _row(db, "bandwidth.download.client_percents.a.b") is None
    deleted = [h.key for h in await _history(db) if h.new_value == "[DELETED]"]
    assert sorted(deleted) == ["bandwidth.download.client_percents.a.b", "qbittorrent.url", "system.log_level"]


# --- what the heal never does -----------------------------------------------------------------------

async def test_an_unhealable_database_is_left_exactly_as_it_was(cm, db, loguru_lines):
    await _drop(db, "bandwidth.download.total_limit")    # required all the way up: no default to fall back to
    await _seed(db, "system.log_level", "LOUD")          # healable on its own
    before, history = await _rows(db), await _history_count(db)

    assert await cm.heal_stored_config(db) == 0

    assert await _rows(db) == before
    assert await _history_count(db) == history
    assert await cm.load_config_from_db(db) is None
    errors = [m for level, m in loguru_lines if level == "ERROR"]
    assert any(m.startswith("Config could not be healed: bandwidth.download.total_limit: ") for m in errors), errors


async def test_the_loader_error_line_never_prints_a_decrypted_secret(cm, db, loguru_lines):
    # Final review: Pydantic's input_value echoed the half-written legacy section, password included.
    await _drop(db, "qbittorrent")
    await _seed(db, "qbittorrent.username", "u")
    await _seed(db, "qbittorrent.password", encrypt_value("AUDITMARK-legacy"))
    await _drop(db, "bandwidth.download.total_limit")

    assert await cm.heal_stored_config(db) == 0
    assert await cm.load_config_from_db(db) is None

    assert not any("AUDITMARK" in m for _, m in loguru_lines)
    errors = [m for level, m in loguru_lines if level == "ERROR"]
    assert any(m.startswith("Failed to construct SpeedarrConfig from database: ") and "bandwidth.download.total_limit" in m
               for m in errors), errors


async def test_a_value_encrypted_with_another_key_is_never_healed(cm, db):
    await _seed(db, "notifications.pushover.user_key", Fernet(Fernet.generate_key()).encrypt(b"x").decode())
    await _seed(db, "system.log_level", "LOUD")
    before = await _rows(db)

    with pytest.raises(ValueError, match="Failed to decrypt"):
        await cm.heal_stored_config(db)

    assert await _rows(db) == before


# --- list rows ------------------------------------------------------------------------------------

@pytest.fixture
async def cm_clients(db):
    manager = _manager()
    await manager.migrate_yaml_to_db(_base(download_clients=_clients()), db)
    return manager


async def _corrupt_list(db, key, mutate):
    """Edit the stored json row the way an older writer might have left it (secret leaves stay tokens)."""
    row = await _row(db, key)
    entries = json.loads(row.value)
    mutate(entries)
    row.value = json.dumps(entries)
    await db.commit()


async def test_a_bad_optional_client_field_is_reset_and_the_others_kept(cm_clients, db, loguru_lines):
    before = (await cm_clients.load_config_from_db(db)).download_clients
    await _corrupt_list(db, "download_clients", lambda e: e[1].__setitem__("max_speed_mbps", "fast"))
    assert await cm_clients.load_config_from_db(db) is None

    assert await cm_clients.heal_stored_config(db) == 1

    after = (await cm_clients.load_config_from_db(db)).download_clients
    assert [c.model_dump() for c in (after[0], after[2])] == [c.model_dump() for c in (before[0], before[2])]
    assert after[1].max_speed_mbps is None and after[1].password == "AUDITMARK-qb1"
    stored = json.loads((await _row(db, "download_clients")).value)
    assert all(looks_like_fernet_token(e["password"]) for e in stored)
    last = (await _history(db, "download_clients"))[-1]
    assert "AUDITMARK" not in (last.old_value or "") + last.new_value and REDACTED in last.new_value
    assert any(w.startswith("Healed config download_clients[qb_1 QB 1].max_speed_mbps: ") for w in _warnings(loguru_lines))


async def test_a_client_missing_a_required_field_is_removed(cm_clients, db, loguru_lines):
    await _corrupt_list(db, "download_clients", lambda e: e[1].pop("url"))

    assert await cm_clients.heal_stored_config(db) == 1

    assert [c.id for c in (await cm_clients.load_config_from_db(db)).download_clients] == ["qb_0", "qb_2"]
    assert any(w.startswith("Healed config download_clients[qb_1 QB 1]: ") and w.endswith("; the entry was removed (audit NEW-2)")
               for w in _warnings(loguru_lines))


async def test_entry_with_a_required_and_an_optional_error_is_removed_once(cm_clients, db):
    # Review Focus 5: one removal, and qb_2 does not shift into qb_1's field reset.
    def mutate(e):
        e[1].pop("url")
        e[1]["max_speed_mbps"] = "fast"
    await _corrupt_list(db, "download_clients", mutate)

    assert await cm_clients.heal_stored_config(db) == 1

    clients = (await cm_clients.load_config_from_db(db)).download_clients
    assert [c.id for c in clients] == ["qb_0", "qb_2"]
    assert clients[1].url == "http://qb2:8080"


async def test_a_secret_bearing_entry_leaves_no_secret_in_logs_or_history(cm_clients, db, loguru_lines):
    await _corrupt_list(db, "download_clients", lambda e: e[1].pop("url"))
    assert await cm_clients.heal_stored_config(db) == 1
    dump = "\n".join(m for _, m in loguru_lines)
    dump += "".join((h.old_value or "") + h.new_value for h in await _history(db))
    assert "AUDITMARK" not in dump
    assert "gAAAA" not in dump


async def test_media_server_bad_field_is_reset_and_the_server_kept(db):
    # Review Focus 4: every MediaServerConfig field has a default.
    manager = _manager()
    servers = [MediaServerConfig(id="plex_1", name="Plex", url="http://plex:32400", token="AUDITMARK-plex")]
    await manager.migrate_yaml_to_db(_base(media_servers=servers), db)
    await _corrupt_list(db, "media_servers", lambda e: e[0].__setitem__("include_lan_streams", "sometimes"))

    assert await manager.heal_stored_config(db) == 1

    loaded = (await manager.load_config_from_db(db)).media_servers
    assert [(s.id, s.include_lan_streams, s.token) for s in loaded] == [("plex_1", False, "AUDITMARK-plex")]


async def test_a_list_row_that_is_not_a_list_goes_back_to_empty(cm_clients, db):
    await _seed(db, "download_clients", json.dumps({"not": "a list"}), "json")
    assert await cm_clients.heal_stored_config(db) == 1
    assert (await cm_clients.load_config_from_db(db)).download_clients == []


# --- fix round 1 ------------------------------------------------------------------------------------

async def test_a_bad_item_in_a_list_valued_scalar_row_resets_the_row(cm, db):
    await _seed(db, "notifications.discord.events", json.dumps(["stream_started", 1]), "json")
    assert await cm.load_config_from_db(db) is None

    assert await cm.heal_stored_config(db) == 1

    assert await _row(db, "notifications.discord.events") is None
    assert (await cm.load_config_from_db(db)).notifications.discord.events is not None
    deleted = [h for h in await _history(db, "notifications.discord.events") if h.new_value == "[DELETED]"]
    assert len(deleted) == 1


async def test_a_failing_parent_and_child_are_healed_once(cm, db, loguru_lines):
    # With autoflush off (production) the parent's deletes are not visible to the child's query.
    await _drop(db, "sabnzbd")
    await _seed(db, "sabnzbd.max_speed_mbps", "fast")
    await _seed(db, "sabnzbd.api_key", encrypt_value("k"))                  # sabnzbd.url is missing
    assert await cm.load_config_from_db(db) is None

    assert await cm.heal_stored_config(db) == 1

    assert [k for k in await _rows(db) if k.startswith("sabnzbd")] == []
    deleted = [h.key for h in await _history(db) if h.new_value == "[DELETED]"]
    assert sorted(deleted) == ["sabnzbd.api_key", "sabnzbd.max_speed_mbps"]
    warnings = _warnings(loguru_lines)
    assert len([w for w in warnings if w.startswith("Healed config sabnzbd: ")]) == 1
    assert not [w for w in warnings if w.startswith("Healed config sabnzbd.max_speed_mbps")]
