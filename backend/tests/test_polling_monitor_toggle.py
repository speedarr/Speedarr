"""On/off toggle gating inside PollingMonitor (issue #78)."""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app.services.polling_monitor import PollingMonitor
from tests.conftest import make_config


def _monitor():
    pm = PollingMonitor.__new__(PollingMonitor)   # bypass __init__/network
    pm.config = make_config()
    pm.notification_service = None
    pm._get_db_session = None
    pm._throttling_disabled = False
    pm._throttling_disabled_until = None
    pm._throttling_disabled_by = None
    pm._throttling_state_lock = asyncio.Lock()
    return pm


async def test_enabled_by_default():
    pm = _monitor()
    assert pm.is_throttling_enabled() is True


async def test_disabled_indefinitely():
    pm = _monitor()
    await pm.set_throttling_state(True, None, "corey")
    assert pm.is_throttling_enabled() is False
    status = pm.get_throttling_status()
    assert status == {
        "throttling_enabled": False,
        "throttling_disabled_until": None,
        "throttling_disabled_by": "corey",
    }


async def test_expired_window_reads_as_enabled_before_any_tick():
    pm = _monitor()
    past = datetime.now(timezone.utc) - timedelta(seconds=1)
    await pm.set_throttling_state(True, past, "corey")
    assert pm.is_throttling_enabled() is True
    assert pm.get_throttling_status()["throttling_enabled"] is True


async def test_check_expiry_flips_and_clears_state():
    pm = _monitor()
    past = datetime.now(timezone.utc) - timedelta(seconds=1)
    await pm.set_throttling_state(True, past, "corey")
    await pm._check_throttling_expiry()
    assert pm._throttling_disabled is False
    assert pm._throttling_disabled_by is None


async def test_check_expiry_noop_while_window_active():
    pm = _monitor()
    future = datetime.now(timezone.utc) + timedelta(hours=1)
    await pm.set_throttling_state(True, future, "corey")
    await pm._check_throttling_expiry()
    assert pm._throttling_disabled is True
    assert pm.is_throttling_enabled() is False


class FakeEngine:
    def __init__(self):
        self.calls = 0
    def calculate_throttle(self, *args, **kwargs):
        self.calls += 1
        return {}


class FakeControllerManager:
    def __init__(self):
        self.applied = []
    async def get_client_stats(self):
        return {}
    async def apply_decisions(self, decisions):
        self.applied.append(decisions)


class FakeDB:
    """Async-context-manager session capturing added ORM objects."""
    def __init__(self, store):
        self.store = store
    async def __aenter__(self):
        return self
    async def __aexit__(self, *exc):
        return False
    def add(self, obj):
        self.store.append(obj)
    async def commit(self):
        pass


def _cycle_monitor(db_store):
    pm = _monitor()
    pm.decision_engine = FakeEngine()
    pm.controller_manager = FakeControllerManager()
    pm._get_db_session = lambda: FakeDB(db_store)
    pm.snmp_monitor = None
    pm._cached_streams = []
    pm._cached_client_stats = {}
    pm._client_unreachable_counts = {}
    pm._client_unreachable_warned = {}
    pm._plex_max_failures = 6
    pm._snmp_consecutive_failures = 0
    pm._snmp_unreachable_warned = False
    pm._reservations = []
    pm._reservations_lock = asyncio.Lock()
    pm._session_bandwidth = {}
    pm._session_bandwidth_lock = asyncio.Lock()
    pm._temporary_limits = None
    pm._temporary_limits_lock = asyncio.Lock()
    pm._restoration_scheduled_at = None
    return pm


async def test_cycle_skips_engine_but_records_metric_while_disabled():
    from app.models.bandwidth import BandwidthMetric
    store = []
    pm = _cycle_monitor(store)
    await pm.set_throttling_state(True, None, "corey")
    await pm._download_poll_cycle()
    assert pm.decision_engine.calls == 0
    assert pm.controller_manager.applied == []
    metrics = [o for o in store if isinstance(o, BandwidthMetric)]
    assert len(metrics) == 1
    assert metrics[0].is_throttled is False


async def test_cycle_runs_engine_when_enabled():
    store = []
    pm = _cycle_monitor(store)
    await pm._download_poll_cycle()
    assert pm.decision_engine.calls == 1


async def test_cycle_auto_reenables_after_expiry():
    store = []
    pm = _cycle_monitor(store)
    past = datetime.now(timezone.utc) - timedelta(seconds=1)
    await pm.set_throttling_state(True, past, "corey")
    await pm._download_poll_cycle()
    assert pm._throttling_disabled is False
    assert pm.decision_engine.calls == 1
