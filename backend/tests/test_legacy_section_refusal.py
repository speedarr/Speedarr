"""The legacy qbittorrent/sabnzbd sections are refused, and a reload crash rolls back (audit NEW-7, D1-5).

Before: a write to the unset legacy section stored child rows beside its stored None row; the reload's
unflatten_dict raised TypeError, which _reload_or_rollback did not catch (ValueError only), so the caller
got a 500 (NEW-7). The PUT handler's response builder also 500ed whenever such a section stayed unset
(D1-5). No panel or wizard writes these sections; download clients live in PUT /api/settings/download-clients.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from sqlalchemy import select, func

from app.api import settings as settings_api
from app.config import (
    SpeedarrConfig, BandwidthConfig, DownloadBandwidthConfig, UploadBandwidthConfig, StreamBandwidthConfig,
)
from app.models.configuration import Configuration, ConfigurationHistory
from app.services.config_manager import ConfigManager


def _base():
    return SpeedarrConfig(bandwidth=BandwidthConfig(
        download=DownloadBandwidthConfig(total_limit=100.0),
        upload=UploadBandwidthConfig(total_limit=50.0),
        streams=StreamBandwidthConfig(),
    ))


@pytest.fixture
async def cm(db):
    state = SimpleNamespace(config=None, polling_monitor=None, decision_engine=None,
                            controller_manager=None, notification_service=None)
    manager = ConfigManager(app=SimpleNamespace(state=state))
    await manager.migrate_yaml_to_db(_base(), db)
    state.config = await manager.load_config_from_db(db)
    manager._reload_services = AsyncMock()
    return manager


async def _rows(db):
    return {r.key: r.value for r in (await db.execute(select(Configuration))).scalars().all()}


async def _history_count(db):
    return (await db.execute(select(func.count()).select_from(ConfigurationHistory))).scalar()


@pytest.mark.parametrize("section", ["qbittorrent", "sabnzbd"])
async def test_legacy_section_write_is_refused_and_writes_nothing(cm, db, section):
    before, history = await _rows(db), await _history_count(db)
    with pytest.raises(ValueError) as exc:
        await cm.update_section(section, {"url": "http://x:8080", "enabled": True}, db)
    assert str(exc.value) == f"Section '{section}' is managed by PUT /api/settings/download-clients"
    assert await _rows(db) == before
    assert await _history_count(db) == history


async def test_api_answers_400_for_a_legacy_section(cm, db):
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(config_manager=cm)))
    body = settings_api.SettingsUpdateRequest(config={"url": "http://x:8080"})
    with pytest.raises(HTTPException) as exc:
        await settings_api.update_section("qbittorrent", body, request, db=db, current_user=SimpleNamespace(id=1))
    assert exc.value.status_code == 400
    assert "/api/settings/download-clients" in exc.value.detail


async def test_a_loader_crash_rolls_back_and_reports_nothing_written(cm, db, monkeypatch):
    before = await _rows(db)

    async def crash(_db):
        raise TypeError("'NoneType' object does not support item assignment")

    monkeypatch.setattr(cm, "load_config_from_db", crash)
    with pytest.raises(ValueError, match="nothing was written"):
        await cm.update_section("system", {"update_frequency": 30}, db)
    monkeypatch.undo()
    assert await _rows(db) == before


async def test_a_normal_section_still_saves(cm, db):
    cfg = await cm.update_section("system", {"update_frequency": 30}, db)
    assert cfg.system.update_frequency == 30
