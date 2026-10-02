"""The controller manager records each torrent client's normal limits once, before it ever writes
to the client, and keeps them across restarts and settings saves (audit T4-5)."""
import asyncio

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.clients.base import RestoreOutcome
from app.config import DownloadClientConfig, FailsafeConfig
from app.database import Base
from app.services import client_baselines
from app.services.controller_manager import ControllerManager
from tests.conftest import make_config

QB, SAB, DE = "qbittorrent_1", "sabnzbd_1", "deluge_1"


class FakeTorrent:
    """A torrent adapter whose limit in force is whatever was last written (like qBittorrent)."""

    restores_saved_cap = False

    def __init__(self, url, download=0.0, upload=0.0, fail_reads=False):
        self.url = url.rstrip("/")
        self.limits = {"download_limit": download, "upload_limit": upload}
        self.fail_reads = fail_reads
        self.writes = []

    async def test_connection(self):
        return True

    async def get_stats(self):
        if self.fail_reads:
            return {"active": False, "error": "timeout"}
        return {"active": False, "download_speed": 0.0, "upload_speed": 0.0, **self.limits}

    async def set_speed_limits(self, download_limit=None, upload_limit=None):
        self.writes.append((download_limit, upload_limit))
        if download_limit is not None:
            self.limits["download_limit"] = download_limit
        if upload_limit is not None:
            self.limits["upload_limit"] = upload_limit

    async def set_unlimited(self):
        await self.set_speed_limits(0, 0)

    async def restore_speed_limits(self, baseline=None):
        if baseline is None:
            return None
        limits = {"download_limit": baseline["download_limit"], "upload_limit": baseline["upload_limit"]}
        await self.set_speed_limits(**limits)
        return limits

    async def close(self):
        pass


class FakeSab(FakeTorrent):
    restores_saved_cap = True


def _config(*clients):
    cfg = make_config()
    cfg.download_clients = [
        DownloadClientConfig(id=cid, type=cid.split("_")[0], name=cid, url=url, enabled=enabled,
                             supports_upload=cid.startswith(("qbittorrent", "deluge")))
        for cid, url, enabled in clients
    ]
    return cfg


@pytest.fixture
async def maker():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def _manager(maker, cfg, adapters, load=True):
    cm = ControllerManager(cfg, maker)
    cm.clients = dict(adapters)
    cm.client_configs = {c.id: c for c in cfg.download_clients if c.id in adapters}
    if load:
        await cm.load_baselines()
    return cm


async def _stored(maker):
    async with maker() as db:
        return await client_baselines.load_baselines(db)


THROTTLE = {"action": "throttle", "download_limit": 30.0, "upload_limit": 5.0, "reason": "t"}


async def test_first_good_poll_captures_before_any_write(maker):
    qb = FakeTorrent("http://qb:8080")
    cm = await _manager(maker, _config((QB, "http://qb:8080", True)), {QB: qb})
    await cm.get_client_stats()
    await cm.apply_decisions({QB: THROTTLE})
    await cm.get_client_stats()
    stored = await _stored(maker)
    assert stored[QB]["download_limit"] == 0.0 and stored[QB]["upload_limit"] == 0.0
    assert stored[QB]["url"] == "http://qb:8080"


async def test_the_audit_ratchet_restart_at_30_restores_unlimited(maker):
    """Audit T4-5 failure: unlimited client, throttled to 30, process restarts, stop restores 30."""
    cfg = _config((QB, "http://qb:8080", True))
    qb = FakeTorrent("http://qb:8080")
    first = await _manager(maker, cfg, {QB: qb})
    await first.get_client_stats()
    await first.apply_decisions({QB: THROTTLE})
    assert qb.limits["download_limit"] == 30.0

    second = await _manager(maker, cfg, {QB: qb})          # new process, client still at 30
    await second.get_client_stats()
    outcomes = await second.restore_all_speeds(retry_delay=0)
    assert outcomes == {QB: RestoreOutcome.RESTORED}
    assert qb.limits == {"download_limit": 0.0, "upload_limit": 0.0}


async def test_reload_clients_keeps_the_record(maker, monkeypatch):
    cfg = _config((QB, "http://qb:8080", True))
    qb = FakeTorrent("http://qb:8080")
    cm = await _manager(maker, cfg, {QB: qb})
    await cm.get_client_stats()
    await cm.apply_decisions({QB: THROTTLE})

    rebuilt = FakeTorrent("http://qb:8080", download=30.0, upload=5.0)
    monkeypatch.setattr("app.services.controller_manager.create_download_client", lambda c: rebuilt)
    await cm.reload_clients(cfg)
    await cm.get_client_stats()
    assert (await _stored(maker))[QB]["download_limit"] == 0.0


async def test_no_capture_after_speedarr_wrote_to_the_client(maker):
    """First read fails, the T3-1 decision still writes, the poll's second read succeeds: no capture."""
    qb = FakeTorrent("http://qb:8080", fail_reads=True)
    cm = await _manager(maker, _config((QB, "http://qb:8080", True)), {QB: qb})
    await cm.get_client_stats()
    await cm.apply_decisions({QB: THROTTLE})
    qb.fail_reads = False
    await cm.get_client_stats()
    assert await _stored(maker) == {}


async def test_a_failed_poll_captures_nothing(maker):
    qb = FakeTorrent("http://qb:8080", fail_reads=True)
    cm = await _manager(maker, _config((QB, "http://qb:8080", True)), {QB: qb})
    await cm.get_client_stats()
    assert await _stored(maker) == {} and cm._baselines == {}


async def test_saved_cap_clients_never_get_a_record(maker):
    sab = FakeSab("http://sab:8080")
    cm = await _manager(maker, _config((SAB, "http://sab:8080", True)), {SAB: sab})
    await cm.get_client_stats()
    assert await _stored(maker) == {}


async def test_failed_load_blocks_capture_until_a_load_succeeds(maker):
    """A transient error at start must not let a capture overwrite the stored row with one client."""
    async with maker() as db:
        await client_baselines.save_baselines(db, {DE: client_baselines.make_record("http://de:8112", 50, 10)})
        await db.commit()
    cfg = _config((QB, "http://qb:8080", True), (DE, "http://de:8112", True))
    qb, de = FakeTorrent("http://qb:8080"), FakeTorrent("http://de:8112")

    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("database is locked")
        return maker()

    cm = ControllerManager(cfg, flaky)
    cm.clients = {QB: qb, DE: de}
    cm.client_configs = {c.id: c for c in cfg.download_clients}
    await cm.load_baselines()
    assert cm._baselines_loaded is False
    await cm.get_client_stats()                               # capture retries the load first
    stored = await _stored(maker)
    assert stored[DE]["download_limit"] == 50.0                # not overwritten
    assert QB in stored


async def test_a_save_failure_retries_on_the_next_poll(maker):
    qb = FakeTorrent("http://qb:8080")
    cfg = _config((QB, "http://qb:8080", True))
    cm = await _manager(maker, cfg, {QB: qb})

    real = cm._get_db_session

    def broken():
        raise RuntimeError("disk I/O error")

    cm._get_db_session = broken
    await cm.get_client_stats()
    assert cm._baselines == {}
    cm._get_db_session = real
    await cm.get_client_stats()
    assert QB in await _stored(maker)


async def test_url_change_drops_the_record_and_allows_a_fresh_capture(maker, monkeypatch):
    qb = FakeTorrent("http://qb:8080")
    cm = await _manager(maker, _config((QB, "http://qb:8080", True)), {QB: qb})
    await cm.get_client_stats()
    await cm.apply_decisions({QB: THROTTLE})

    moved = FakeTorrent("http://qb-new:8080", download=12.0, upload=3.0)
    monkeypatch.setattr("app.services.controller_manager.create_download_client", lambda c: moved)
    await cm.reload_clients(_config((QB, "http://qb-new:8080", True)))
    assert QB not in await _stored(maker)
    await cm.get_client_stats()
    stored = await _stored(maker)
    assert stored[QB]["url"] == "http://qb-new:8080" and stored[QB]["download_limit"] == 12.0


async def test_removal_prunes_and_a_disabled_client_keeps_its_record(maker, monkeypatch):
    qb, de = FakeTorrent("http://qb:8080"), FakeTorrent("http://de:8112")
    cfg = _config((QB, "http://qb:8080", True), (DE, "http://de:8112", True))
    cm = await _manager(maker, cfg, {QB: qb, DE: de})
    await cm.get_client_stats()
    assert set(await _stored(maker)) == {QB, DE}

    monkeypatch.setattr("app.services.controller_manager.create_download_client", lambda c: qb)
    await cm.reload_clients(_config((QB, "http://qb:8080/", False)))   # DE removed, QB disabled + slash
    assert set(await _stored(maker)) == {QB}


async def test_load_prunes_records_for_clients_no_longer_configured(maker):
    async with maker() as db:
        await client_baselines.save_baselines(db, {
            QB: client_baselines.make_record("http://qb:8080", 0, 0),
            DE: client_baselines.make_record("http://de:8112", 0, 0),
        })
        await db.commit()
    await _manager(maker, _config((QB, "http://qb:8080", True)), {})
    assert set(await _stored(maker)) == {QB}


async def test_no_session_factory_means_no_capture_and_no_error():
    qb = FakeTorrent("http://qb:8080")
    cm = ControllerManager(_config((QB, "http://qb:8080", True)))
    cm.clients = {QB: qb}
    await cm.load_baselines()
    stats = await cm.get_client_stats()
    assert "error" not in stats[QB] and cm._baselines == {}


async def test_a_torrent_client_without_a_record_is_nothing_to_restore(maker):
    qb = FakeTorrent("http://qb:8080", fail_reads=True)
    cm = await _manager(maker, _config((QB, "http://qb:8080", True)), {QB: qb})
    assert await cm.restore_all_speeds(retry_delay=0) == {QB: RestoreOutcome.NOTHING_TO_RESTORE}
    assert qb.writes == []


class GatedTorrent(FakeTorrent):
    """Holds get_stats until released, to land a reload in the middle of a poll."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.gate = asyncio.Event()
        self.reading = asyncio.Event()

    async def get_stats(self):
        stats = await super().get_stats()
        self.reading.set()
        await self.gate.wait()
        return stats


async def test_a_capture_in_flight_during_a_reload_is_discarded(maker, monkeypatch):
    old = GatedTorrent("http://qb-old:8080", download=40.0, upload=4.0)
    cm = await _manager(maker, _config((QB, "http://qb-old:8080", True)), {QB: old})
    poll = asyncio.create_task(cm.get_client_stats())
    await old.reading.wait()

    new = FakeTorrent("http://qb-new:8080", download=12.0, upload=3.0)
    monkeypatch.setattr("app.services.controller_manager.create_download_client", lambda c: new)
    await cm.reload_clients(_config((QB, "http://qb-new:8080", True)))
    old.gate.set()
    await poll
    assert await _stored(maker) == {} and cm._baselines == {}

    await cm.get_client_stats()
    stored = await _stored(maker)
    assert stored[QB]["url"] == "http://qb-new:8080" and stored[QB]["download_limit"] == 12.0


async def test_a_same_url_reload_keeps_the_written_mark(maker, monkeypatch):
    qb = FakeTorrent("http://qb:8080", fail_reads=True)
    cfg = _config((QB, "http://qb:8080", True))
    cm = await _manager(maker, cfg, {QB: qb})
    await cm.get_client_stats()
    await cm.apply_decisions({QB: THROTTLE})
    rebuilt = FakeTorrent("http://qb:8080", download=30.0, upload=5.0)
    monkeypatch.setattr("app.services.controller_manager.create_download_client", lambda c: rebuilt)
    await cm.reload_clients(cfg)
    await cm.get_client_stats()
    assert await _stored(maker) == {}


async def test_remove_all_limits_marks_the_client_written(maker):
    qb = FakeTorrent("http://qb:8080", fail_reads=True)
    cm = await _manager(maker, _config((QB, "http://qb:8080", True)), {QB: qb})
    await cm.remove_all_limits()
    qb.fail_reads = False
    await cm.get_client_stats()
    assert await _stored(maker) == {}


async def test_shutdown_speeds_mark_the_client_written(maker):
    qb = FakeTorrent("http://qb:8080", fail_reads=True)
    cm = await _manager(maker, _config((QB, "http://qb:8080", True)), {QB: qb})
    await cm.apply_shutdown_speeds(FailsafeConfig(shutdown_download_speed=10.0), retry_delay=0)
    qb.fail_reads = False
    await cm.get_client_stats()
    assert await _stored(maker) == {}


async def test_a_restore_that_writes_marks_the_client_written(maker):
    sab = FakeSab("http://sab:8080")
    cm = await _manager(maker, _config((SAB, "http://sab:8080", True)), {SAB: sab})
    assert SAB not in cm._written
    await cm.restore_all_speeds(retry_delay=0)
    assert SAB in cm._written


async def test_a_torrent_restore_marks_the_client_so_it_is_not_recaptured(maker):
    qb = FakeTorrent("http://qb:8080")
    cm = await _manager(maker, _config((QB, "http://qb:8080", True)), {QB: qb})
    await cm.get_client_stats()
    await cm.restore_all_speeds(retry_delay=0)
    cm._baselines.pop(QB)
    assert QB in cm._written
    await cm.get_client_stats()
    assert QB not in cm._baselines
