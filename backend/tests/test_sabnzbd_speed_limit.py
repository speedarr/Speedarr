"""SABnzbd must send a non-zero wire value for tiny throttles (issue #43)."""
import asyncio
from unittest.mock import AsyncMock

from app.clients.sabnzbd import SABnzbdClient


def _captured_value(download_limit):
    client = SABnzbdClient("http://localhost:8080", "apikey")
    client._api_call = AsyncMock(return_value={})
    asyncio.run(client.set_speed_limits(download_limit=download_limit))
    args, _ = client._api_call.call_args
    # set_speed_limits calls _api_call("config", {"name": "speedlimit", "value": <value>})
    return args[1]["value"]


def test_hard_min_trickle_is_non_zero():
    # 0.01 Mbps (HARD_MIN) must NOT collapse to an "unlimited" value
    value = _captured_value(0.01)
    assert value not in ("0", "0.0M", "0.0K", "0K")
    assert value == "1K"


def test_normal_limit_converts_correctly():
    assert _captured_value(80.0) == "10000K"


def test_one_mbps_is_non_zero():
    assert _captured_value(1.0) == "125K"
