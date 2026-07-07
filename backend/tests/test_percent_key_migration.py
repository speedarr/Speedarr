"""Per-client percent keys migrate from client type to client id."""
import pytest
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.database import Base
from app.models.configuration import Configuration
from app.services.config_manager import ConfigManager, resolve_percent_key, normalize_percent_dict
from app.config import (
    SpeedarrConfig, BandwidthConfig, DownloadBandwidthConfig,
    UploadBandwidthConfig, StreamBandwidthConfig, DownloadClientConfig,
)


def _c(cid, ctype):
    return SimpleNamespace(id=cid, type=ctype)


def test_resolve_keeps_id_exact():
    clients = [_c("qbittorrent_1", "qbittorrent"), _c("qbittorrent_2", "qbittorrent")]
    assert resolve_percent_key("qbittorrent_1", clients) == "qbittorrent_1"


def test_resolve_drops_ambiguous_type():
    clients = [_c("qbittorrent_1", "qbittorrent"), _c("qbittorrent_2", "qbittorrent")]
    assert resolve_percent_key("qbittorrent", clients) is None


def test_resolve_renames_single_type_match():
    clients = [_c("qbittorrent_9", "qbittorrent")]
    assert resolve_percent_key("qbittorrent", clients) == "qbittorrent_9"


def test_resolve_drops_unknown_key():
    clients = [_c("qbittorrent_1", "qbittorrent")]
    assert resolve_percent_key("deluge", clients) is None


def test_normalize_prefers_id_over_type():
    clients = [_c("qbittorrent_9", "qbittorrent")]
    out, changed = normalize_percent_dict({"qbittorrent": 30, "qbittorrent_9": 70}, clients)
    assert out == {"qbittorrent_9": 70}  # id-exact wins; type rename target is taken -> dropped
    assert changed is True


def test_normalize_renames_single_type():
    clients = [_c("qbittorrent_9", "qbittorrent")]
    out, changed = normalize_percent_dict({"qbittorrent": 80}, clients)
    assert out == {"qbittorrent_9": 80}
    assert changed is True


def test_normalize_noop_when_already_id_keyed():
    clients = [_c("qbittorrent_1", "qbittorrent"), _c("qbittorrent_2", "qbittorrent")]
    out, changed = normalize_percent_dict({"qbittorrent_1": 60, "qbittorrent_2": 40}, clients)
    assert out == {"qbittorrent_1": 60, "qbittorrent_2": 40}
    assert changed is False


@pytest.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as session:
        yield session
    await engine.dispose()


def _client(cid, ctype, supports_upload=True):
    return DownloadClientConfig(
        id=cid, type=ctype, name=cid, url="http://localhost", supports_upload=supports_upload
    )


def _config_with_clients(clients):
    return SpeedarrConfig(
        bandwidth=BandwidthConfig(
            download=DownloadBandwidthConfig(total_limit=100.0),
            upload=UploadBandwidthConfig(total_limit=50.0),
            streams=StreamBandwidthConfig(),
        ),
        download_clients=clients,
    )


async def _seed(db, key, value):
    db.add(Configuration(key=key, value=str(value), value_type="integer"))
    await db.commit()


async def _keys_under(db, prefix):
    rows = (await db.execute(
        select(Configuration).where(Configuration.key.startswith(prefix))
    )).scalars().all()
    return {r.key for r in rows}


async def test_migrate_drops_ambiguous_collision_key(db):
    cm = ConfigManager(app=None)
    config = _config_with_clients([_client("qbittorrent_1", "qbittorrent"),
                                   _client("qbittorrent_2", "qbittorrent")])
    await _seed(db, "bandwidth.download.client_percents.qbittorrent", 60)
    changed = await cm.migrate_client_percent_keys(config, db)
    assert changed is True
    assert await _keys_under(db, "bandwidth.download.client_percents.") == set()


async def test_migrate_renames_single_type_match(db):
    cm = ConfigManager(app=None)
    config = _config_with_clients([_client("qbittorrent_9", "qbittorrent")])
    await _seed(db, "bandwidth.upload.upload_client_percents.qbittorrent", 80)
    await cm.migrate_client_percent_keys(config, db)
    assert await _keys_under(db, "bandwidth.upload.upload_client_percents.") == {
        "bandwidth.upload.upload_client_percents.qbittorrent_9"
    }


async def test_migrate_keeps_id_exact_and_is_idempotent(db):
    cm = ConfigManager(app=None)
    config = _config_with_clients([_client("qbittorrent", "qbittorrent")])
    await _seed(db, "bandwidth.download.client_percents.qbittorrent", 100)
    first = await cm.migrate_client_percent_keys(config, db)
    second = await cm.migrate_client_percent_keys(config, db)
    assert first is False and second is False
    assert await _keys_under(db, "bandwidth.download.client_percents.") == {
        "bandwidth.download.client_percents.qbittorrent"
    }


async def test_migrate_drops_dead_type_key(db):
    cm = ConfigManager(app=None)
    config = _config_with_clients([_client("qbittorrent_1", "qbittorrent")])
    await _seed(db, "bandwidth.download.client_percents.deluge", 50)
    changed = await cm.migrate_client_percent_keys(config, db)
    assert changed is True
    assert await _keys_under(db, "bandwidth.download.client_percents.") == set()


async def test_cleanup_bandwidth_percent_keys_clears_all_prefixes(db):
    cm = ConfigManager(app=None)
    await _seed(db, "bandwidth.download.client_percents.qbittorrent_1", 60)
    await _seed(db, "bandwidth.upload.upload_client_percents.qbittorrent_1", 70)
    await _seed(db, "bandwidth.download.scheduled.client_percents.qbittorrent_1", 50)
    await _seed(db, "bandwidth.upload.scheduled.client_percents.qbittorrent_1", 50)
    await cm.cleanup_bandwidth_percent_keys(db)
    await db.commit()
    remaining = (await db.execute(select(Configuration))).scalars().all()
    assert remaining == []


def test_prune_percent_dicts_keeps_only_valid_ids():
    from app.api.settings import _prune_percent_dicts
    data = {
        "bandwidth": {
            "download": {
                "client_percents": {"qb_1": 60, "qb_2": 40, "stale": 10},
                "scheduled": {"client_percents": {"qb_1": 50, "gone": 5}},
            },
            "upload": {
                "upload_client_percents": {"qb_1": 70, "gone": 5},
                "scheduled": {"client_percents": {}},
            },
        },
        "failsafe": {
            "shutdown_download_client_percents": {"qb_1": 100, "x": 1},
            "shutdown_upload_client_percents": {},
        },
    }
    _prune_percent_dicts(data, {"qb_1", "qb_2"})
    assert data["bandwidth"]["download"]["client_percents"] == {"qb_1": 60, "qb_2": 40}
    assert data["bandwidth"]["download"]["scheduled"]["client_percents"] == {"qb_1": 50}
    assert data["bandwidth"]["upload"]["upload_client_percents"] == {"qb_1": 70}
    assert data["failsafe"]["shutdown_download_client_percents"] == {"qb_1": 100}
