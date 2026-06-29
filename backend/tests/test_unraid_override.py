"""Unraid override slot + most-restrictive combine (issue #30)."""
import pytest

from app.config import UnraidConfig
from app.services.unraid_monitor import UnraidStatus
from app.services.polling_monitor import PollingMonitor, most_restrictive
from tests.conftest import make_config


def test_most_restrictive():
    assert most_restrictive(None, None) is None
    assert most_restrictive(5.0, None) == 5.0
    assert most_restrictive(None, 3.0) == 3.0
    assert most_restrictive(5.0, 3.0) == 3.0
    assert most_restrictive(0.0, 3.0) == 0.0  # 0 wins; flooring happens downstream


def _monitor(**unraid_kwargs):
    cfg = make_config()
    cfg.unraid = UnraidConfig(enabled=True, url="http://tower", api_key="k",
                              download_limit_mbps=5, upload_limit_mbps=5, **unraid_kwargs)
    # decision_engine / controller_manager unused by the methods under test
    return PollingMonitor(cfg, decision_engine=None, controller_manager=None)


async def test_apply_status_sets_override_when_condition_active():
    pm = _monitor()
    await pm._apply_unraid_status(UnraidStatus(True, False, False, "STARTED", 10))
    dl, ul = await pm.get_unraid_override_limits()
    assert (dl, ul) == (5, 5)
    assert pm._unraid_override["reasons"] == ["parity_check"]
    assert pm._unraid_override["holding"] is False


async def test_apply_status_clears_override_when_idle():
    pm = _monitor()
    await pm._apply_unraid_status(UnraidStatus(True, False, False, "STARTED", 10))
    await pm._apply_unraid_status(UnraidStatus(False, False, False, "STARTED", None))
    assert pm._unraid_override is None
    assert await pm.get_unraid_override_limits() == (None, None)


async def test_apply_status_none_holds_last_known():
    pm = _monitor()
    await pm._apply_unraid_status(UnraidStatus(True, False, False, "STARTED", 10))
    await pm._apply_unraid_status(None)  # API unreachable
    dl, ul = await pm.get_unraid_override_limits()
    assert (dl, ul) == (5, 5)               # held
    assert pm._unraid_override["holding"] is True


async def test_no_override_when_no_limits_active():
    pm = _monitor()
    assert await pm.get_unraid_override_limits() == (None, None)
