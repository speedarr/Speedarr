"""Persisted normal limits for the torrent clients (audit T4-5)."""
import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from loguru import logger as loguru_logger
from sqlalchemy import select

from app.config import DownloadClientConfig
from app.models.configuration import Configuration
from app.services.client_baselines import (
    KEY, load_baselines, make_record, prune_baselines, save_baselines,
)
from app.services.config_manager import ConfigManager
from tests.test_full_config_removes_stale_keys import _base, _manager

NOW = datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc)


def _cfg(cid, url, enabled=True):
    return DownloadClientConfig(id=cid, type=cid.split("_")[0], name=cid, url=url, enabled=enabled)


@pytest.fixture
def log(caplog):
    handler_id = loguru_logger.add(caplog.handler, level="WARNING", format="{message}")
    yield caplog
    loguru_logger.remove(handler_id)


def test_make_record_normalises_the_url_and_stamps_utc():
    record = make_record("http://qb:8080/", 0, 20, now=NOW)
    assert record == {"url": "http://qb:8080", "download_limit": 0.0, "upload_limit": 20.0,
                      "captured_at": "2026-10-02T12:00:00+00:00"}


async def test_absent_row_loads_empty(db):
    assert await load_baselines(db) == {}


async def test_round_trip(db):
    records = {"qbittorrent_1": make_record("http://qb:8080", 0, 20, now=NOW),
               "deluge_1": make_record("http://de:8112", 50, 10, now=NOW)}
    await save_baselines(db, records)
    await db.commit()
    assert await load_baselines(db) == records
    await save_baselines(db, {"deluge_1": records["deluge_1"]})
    await db.commit()
    assert await load_baselines(db) == {"deluge_1": records["deluge_1"]}
    rows = (await db.execute(select(Configuration).where(Configuration.key == KEY))).scalars().all()
    assert len(rows) == 1 and rows[0].value_type == "json"


@pytest.mark.parametrize("value", ["{not json", "[1, 2]", "null"])
async def test_a_malformed_row_loads_empty_with_a_warning(db, log, value):
    db.add(Configuration(key=KEY, value=value, value_type="json"))
    await db.commit()
    assert await load_baselines(db) == {}
    assert any(KEY in r.getMessage() for r in log.records)


async def test_a_malformed_entry_is_dropped_and_the_rest_kept(db, log):
    good = make_record("http://qb:8080", 0, 20, now=NOW)
    db.add(Configuration(key=KEY, value=json.dumps({
        "qbittorrent_1": good,
        "deluge_1": {"url": "http://de", "download_limit": "fast", "upload_limit": 0, "captured_at": "x"},
        "transmission_1": {"url": "http://tr", "download_limit": -1, "upload_limit": 0, "captured_at": "x"},
        "qbittorrent_2": "nonsense",
    }), value_type="json"))
    await db.commit()
    assert await load_baselines(db) == {"qbittorrent_1": good}
    messages = [r.getMessage() for r in log.records]
    assert sum("Ignoring malformed baseline" in m for m in messages) == 3


async def test_the_row_survives_a_full_config_write(db):
    cm = _manager()
    await cm.migrate_yaml_to_db(_base(), db)
    await save_baselines(db, {"qbittorrent_1": make_record("http://qb:8080", 0, 20, now=NOW)})
    await db.commit()
    await cm.update_full_config(_base().model_dump(), db)
    assert "qbittorrent_1" in await load_baselines(db)


def test_prune_keeps_matching_ids_including_disabled_and_trailing_slash():
    records = {
        "qbittorrent_1": make_record("http://qb:8080", 0, 20, now=NOW),
        "deluge_1": make_record("http://de:8112", 0, 0, now=NOW),
        "transmission_1": make_record("http://tr:9091", 0, 0, now=NOW),
        "gone_1": make_record("http://gone", 0, 0, now=NOW),
    }
    clients = [
        _cfg("qbittorrent_1", "http://qb:8080/"),               # trailing slash: same address
        _cfg("deluge_1", "http://de:8112", enabled=False),      # disabled: kept
        _cfg("transmission_1", "http://tr-new:9091"),           # moved: dropped
    ]
    assert set(prune_baselines(records, clients)) == {"qbittorrent_1", "deluge_1"}


def test_prune_of_nothing_is_nothing():
    assert prune_baselines({}, [_cfg("qbittorrent_1", "http://qb")]) == {}
