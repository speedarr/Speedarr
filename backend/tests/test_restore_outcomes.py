"""restore_all_speeds and POST /api/control/restore-speeds tell restored, nothing to restore and
failed apart (audit D3-3)."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from loguru import logger as loguru_logger

from app.api.control import RestoreSpeedsRequest, restore_speeds
from app.clients.base import RestoreOutcome
from app.config import FailsafeConfig
from app.services.controller_manager import (
    ControllerManager, describe_limits, restore_counts, restore_message,
)
from tests.conftest import make_config

R, N, F = RestoreOutcome.RESTORED, RestoreOutcome.NOTHING_TO_RESTORE, RestoreOutcome.FAILED
LIMITS = {"download_limit": 0.0, "upload_limit": 20.0}


class FakeAdapter:
    """Scripted restore: each call pops the next step (a dict, None, or an exception)."""

    def __init__(self, *steps, saved_cap=False, original=None):
        self.steps = list(steps)
        self.restores_saved_cap = saved_cap
        self._original_limits = original
        self.restore_calls = []
        self.set_calls = []

    async def restore_speed_limits(self, baseline=None):
        self.restore_calls.append(baseline)
        step = self.steps.pop(0) if len(self.steps) > 1 else self.steps[0]
        if isinstance(step, Exception):
            raise step
        return step

    async def set_speed_limits(self, download_limit=None, upload_limit=None):
        self.set_calls.append((download_limit, upload_limit))


def _manager(clients, upload=None):
    cm = ControllerManager(make_config())
    cm.clients = dict(clients)
    upload = upload or {}
    cm.client_configs = {cid: SimpleNamespace(supports_upload=upload.get(cid, True)) for cid in clients}
    cm._baselines = {cid: a._original_limits for cid, a in clients.items() if getattr(a, "_original_limits", None) is not None}
    return cm


@pytest.fixture
def log(caplog):
    handler_id = loguru_logger.add(caplog.handler, level="DEBUG", format="{message}")
    yield caplog
    loguru_logger.remove(handler_id)


def _lines(caplog):
    return [r.getMessage() for r in caplog.records]


# --- restore_all_speeds ---------------------------------------------------------

async def test_one_run_reports_all_three_outcomes(log):
    qb = FakeAdapter(LIMITS, original=LIMITS)
    de = FakeAdapter(None)
    sab = FakeAdapter(ConnectionError("down"), saved_cap=True)
    cm = _manager({"qbittorrent_1": qb, "deluge_1": de, "sabnzbd_1": sab}, upload={"sabnzbd_1": False})

    outcomes = await cm.restore_all_speeds(retry_delay=0)

    assert outcomes == {"qbittorrent_1": R, "deluge_1": N, "sabnzbd_1": F}
    lines = _lines(log)
    assert "Restored qbittorrent_1 to its normal limits (DL unlimited, UL 20.0 Mbps)" in lines
    assert "Nothing to restore for deluge_1: Speedarr has never read its limits" in lines
    assert "Failed to restore sabnzbd_1 after 3 attempts: down" in lines
    assert "Restore finished: 1 restored, 1 nothing to restore, 1 failed" in lines
    assert not any(l.startswith(("Restored deluge_1", "Restored sabnzbd_1")) for l in lines)


async def test_nothing_to_restore_is_not_retried():
    de = FakeAdapter(None)
    await _manager({"deluge_1": de}).restore_all_speeds(retry_delay=0)
    assert len(de.restore_calls) == 1


async def test_an_exception_is_retried_then_failed():
    sab = FakeAdapter(ConnectionError("down"), saved_cap=True)
    outcomes = await _manager({"sabnzbd_1": sab}).restore_all_speeds(retries=3, retry_delay=0)
    assert outcomes == {"sabnzbd_1": F}
    assert len(sab.restore_calls) == 3


async def test_a_flaky_client_is_restored_on_retry(log):
    qb = FakeAdapter(ConnectionError("blip"), LIMITS, original=LIMITS)
    outcomes = await _manager({"qbittorrent_1": qb}).restore_all_speeds(retry_delay=0)
    assert outcomes == {"qbittorrent_1": R}
    assert "Failed to restore qbittorrent_1 (attempt 1/3): blip" in _lines(log)


async def test_a_saved_cap_client_is_handed_no_baseline():
    sab = FakeAdapter({"download_limit": 50.0, "upload_limit": 0.0}, saved_cap=True,
                      original={"download_limit": 9.0, "upload_limit": 0.0})
    await _manager({"sabnzbd_1": sab}).restore_all_speeds(retry_delay=0)
    assert sab.restore_calls == [None]


async def test_a_torrent_client_is_handed_its_baseline():
    qb = FakeAdapter(LIMITS, original=LIMITS)
    await _manager({"qbittorrent_1": qb}).restore_all_speeds(retry_delay=0)
    assert qb.restore_calls == [LIMITS]


async def test_a_download_only_client_logs_no_upload_figure(log):
    sab = FakeAdapter({"download_limit": 50.0, "upload_limit": 0.0}, saved_cap=True)
    await _manager({"sabnzbd_1": sab}, upload={"sabnzbd_1": False}).restore_all_speeds(retry_delay=0)
    assert "Restored sabnzbd_1 to its normal limits (DL 50.0 Mbps)" in _lines(log)


async def test_no_clients_returns_empty():
    assert await _manager({}).restore_all_speeds() == {}


# --- apply_decisions restore branch, apply_shutdown_speeds ------------------------

async def test_apply_decisions_restore_branch_is_true_only_when_restored():
    qb = FakeAdapter(LIMITS, original=LIMITS)
    de = FakeAdapter(None)
    cm = _manager({"qbittorrent_1": qb, "deluge_1": de})
    results = await cm.apply_decisions({
        "qbittorrent_1": {"action": "restore", "reason": "t"},
        "deluge_1": {"action": "restore", "reason": "t"},
    })
    assert results == {"qbittorrent_1": True, "deluge_1": False}


async def test_shutdown_speeds_log_the_restore_outcome_per_direction(log):
    qb = FakeAdapter(LIMITS, original=LIMITS)
    de = FakeAdapter(None)
    cm = _manager({"qbittorrent_1": qb, "deluge_1": de})
    results = await cm.apply_shutdown_speeds(FailsafeConfig(shutdown_download_speed=10.0), retry_delay=0)
    assert results == {"qbittorrent_1": True, "deluge_1": True}
    lines = _lines(log)
    assert "Shutdown speeds applied to qbittorrent_1: DL=5.0 Mbps, UL=restored" in lines
    assert "Shutdown speeds applied to deluge_1: DL=5.0 Mbps, UL=nothing to restore" in lines
    assert de.set_calls == [(5.0, None)]


# --- pure helpers -----------------------------------------------------------------

def test_describe_limits():
    assert describe_limits({"download_limit": 0.0, "upload_limit": 20.0}, True) == "DL unlimited, UL 20.0 Mbps"
    assert describe_limits({"download_limit": 96.71, "upload_limit": 0.0}, False) == "DL 96.7 Mbps"


@pytest.mark.parametrize("outcomes, message", [
    ({}, "No download clients configured"),
    ({"qbittorrent_1": R}, "Restored 1 client"),
    ({"qbittorrent_1": R, "deluge_1": R}, "Restored all 2 clients"),
    ({"sabnzbd_1": F}, "Restored 0 of 1 client; failed: sabnzbd_1"),
    ({"qbittorrent_1": R, "transmission_1": R, "nzbget_1": R, "deluge_1": N, "sabnzbd_1": F},
     "Restored 3 of 5 clients; nothing to restore: deluge_1; failed: sabnzbd_1"),
    ({"deluge_1": N, "deluge_2": N},
     "Restored 0 of 2 clients; nothing to restore: deluge_1, deluge_2"),
])
def test_restore_message(outcomes, message):
    assert restore_message(outcomes) == message


def test_restore_counts_always_names_all_three():
    assert restore_counts({"a": R}) == "1 restored, 0 nothing to restore, 0 failed"


# --- POST /api/control/restore-speeds -------------------------------------------------

def _request(outcomes):
    cm = SimpleNamespace(restore_all_speeds=AsyncMock(return_value=outcomes),
                         get_client_stats=AsyncMock(return_value={}))
    ns = SimpleNamespace(notify=AsyncMock())
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(
        controller_manager=cm, notification_service=ns)))


async def test_restore_speeds_reports_outcomes_and_an_honest_message():
    request = _request({"qbittorrent_1": R, "deluge_1": N, "sabnzbd_1": F})
    body = await restore_speeds(request, RestoreSpeedsRequest(), SimpleNamespace(username="admin"))
    assert body["results"] == {"qbittorrent_1": True, "deluge_1": False, "sabnzbd_1": False}
    assert body["outcomes"] == {"qbittorrent_1": "restored", "deluge_1": "nothing_to_restore",
                                "sabnzbd_1": "failed"}
    assert body["message"] == "Restored 1 of 3 clients; nothing to restore: deluge_1; failed: sabnzbd_1"
    assert body["restored_by"] == "admin"


async def test_restore_speeds_with_no_clients():
    body = await restore_speeds(_request({}), RestoreSpeedsRequest(), SimpleNamespace(username="admin"))
    assert body["message"] == "No download clients configured"
    assert body["results"] == {} and body["outcomes"] == {}
