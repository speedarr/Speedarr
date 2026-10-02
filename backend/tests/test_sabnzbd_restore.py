"""SABnzbd goes back to the cap saved in its own settings, not to unlimited (audit T4-6).

SABnzbd keeps the limit in force (queue speedlimit, which Speedarr writes and which SABnzbd
forgets on restart) apart from its saved misc.bandwidth_perc of misc.bandwidth_max, which its
own startup applies. Restore writes the saved percent back as a bare number, as that startup does.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import aiohttp
import pytest

from app.clients.sabnzbd import SABnzbdClient, _sab_bytes
from app.config import FailsafeConfig
from app.services.controller_manager import ControllerManager
from tests.conftest import make_config


def _client(misc):
    client = SABnzbdClient("http://localhost:8080", "key")

    async def api(mode, params=None):
        if mode == "get_config":
            assert params == {"section": "misc"}
            return {"config": {"misc": misc}}
        return {"status": True}

    client._api_call = AsyncMock(side_effect=api)
    return client


def _writes(client):
    return [c.args[1]["value"] for c in client._api_call.call_args_list if c.args[0] == "config"]


@pytest.mark.parametrize("text, expected", [
    ("112M", 112 * 1024 ** 2), ("500K", 500 * 1024), ("1G", 1024 ** 3), ("1048576", 1048576.0),
    ("", 0.0), (None, 0.0), ("fast", 0.0), (" 10m ", 10 * 1024 ** 2),
])
def test_sab_bytes(text, expected):
    assert _sab_bytes(text) == expected


async def test_restore_writes_the_saved_percent_and_never_zero():
    """The audit's scenario: a cap set in SABnzbd itself survives Speedarr letting go."""
    client = _client({"bandwidth_perc": 10, "bandwidth_max": "100M"})
    limits = await client.restore_speed_limits(None)
    assert _writes(client) == ["10"]
    assert limits["download_limit"] == pytest.approx(100 * 1024 ** 2 * 0.10 * 8 / 1e6)  # 10% of 100 MiB/s
    assert limits["upload_limit"] == 0.0


async def test_restore_at_100_percent_writes_100():
    client = _client({"bandwidth_perc": 100, "bandwidth_max": "112M"})
    limits = await client.restore_speed_limits(None)
    assert _writes(client) == ["100"]
    assert limits["download_limit"] == pytest.approx(112 * 1024 ** 2 * 8 / 1e6)


async def test_restore_without_bandwidth_max_reports_unlimited():
    client = _client({"bandwidth_perc": 100, "bandwidth_max": ""})
    limits = await client.restore_speed_limits(None)
    assert _writes(client) == ["100"]
    assert limits == {"download_limit": 0.0, "upload_limit": 0.0}


async def test_restore_ignores_any_baseline_it_is_handed():
    client = _client({"bandwidth_perc": 40, "bandwidth_max": ""})
    await client.restore_speed_limits({"download_limit": 9.0, "upload_limit": 0.0})
    assert _writes(client) == ["40"]


async def test_a_config_reply_without_bandwidth_perc_raises_and_writes_nothing():
    client = _client({"bandwidth_max": "112M"})
    with pytest.raises(ValueError):
        await client.restore_speed_limits(None)
    assert _writes(client) == []


async def test_a_failed_get_config_raises():
    client = SABnzbdClient("http://localhost:8080", "key")
    client._api_call = AsyncMock(side_effect=aiohttp.ClientError("down"))
    with pytest.raises(aiohttp.ClientError):
        await client.restore_speed_limits(None)


async def test_upload_only_shutdown_speeds_leave_sabnzbd_at_its_saved_cap():
    """Knock-on in the audit: restore first (was: unlimited), then no download overlay for SABnzbd."""
    client = _client({"bandwidth_perc": 50, "bandwidth_max": "100M"})
    cm = ControllerManager(make_config())
    cm.clients = {"sabnzbd_1": client}
    cm.client_configs = {"sabnzbd_1": SimpleNamespace(supports_upload=False)}
    results = await cm.apply_shutdown_speeds(FailsafeConfig(shutdown_upload_speed=5.0), retry_delay=0)
    assert results == {"sabnzbd_1": True}
    assert _writes(client) == ["50"]


async def test_stats_no_longer_carry_an_original_limit():
    client = SABnzbdClient("http://localhost:8080", "key")
    client._api_call = AsyncMock(return_value={"queue": {"kbpersec": "0", "speedlimit_abs": "1048576",
                                                         "noofslots": 0}})
    stats = await client.get_stats()
    assert "original_download_limit" not in stats
    assert not hasattr(client, "_original_limit")
