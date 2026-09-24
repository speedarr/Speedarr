"""SNMP interface discovery and speed polling refuse the masked community string (final-review Fix 2).

Since GET /section/snmp masks the community string, the SNMP tab posts the placeholder back to
these two endpoints unless the caller explicitly retyped it. SNMPConfig(**config_data) accepts the
placeholder as a valid (if wrong) community string, so without a guard the device never answers and
the operator sees a misleading "No interfaces discovered" message. Pattern: test_settings_test_connection.py.
"""
from unittest.mock import patch

import pytest

from app.api import settings
from app.config import REDACTED


class _MustNotConstruct:
    def __init__(self, *args, **kwargs):
        raise AssertionError("must not be constructed")


async def test_discover_refuses_masked_community():
    test_request = settings.TestConnectionRequest(
        config={"host": "192.168.1.1", "community": REDACTED},
        use_existing=False,
    )
    with patch("app.services.snmp_monitor.SNMPMonitor", _MustNotConstruct):
        resp = await settings.discover_snmp_interfaces(test_request, current_user=None)

    assert resp["success"] is False
    assert "masked community" in resp["message"]
    assert resp["interfaces"] == []
    assert resp["suggested_wan"] is None


async def test_poll_speeds_refuses_masked_community():
    request = settings.PollSpeedsRequest(
        config={"host": "192.168.1.1", "community": REDACTED},
        interface_indices=[1, 2],
    )
    with patch("app.services.snmp_monitor.SNMPMonitor", _MustNotConstruct):
        resp = await settings.poll_snmp_speeds(request, current_user=None)

    assert resp["success"] is False
    assert "masked community" in resp["message"]
    assert resp["speeds"] == {}
