"""SNMP walk — _walk_oid must parse pysnmp 7.x's flat varBinds shape.

Regression guard for the pysnmp-lextudio 6.x -> pysnmp 7.x migration: 6.x
nextCmd returned a 2-D list-of-rows ([[ObjectType, ...]]), 7.x next_cmd
returns a flat tuple of ObjectType. Iterating the flat shape with the old
nested loop would unpack each (name, value) pair as if it were a row and
silently corrupt interface discovery, so these tests pin the flat contract.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.config import SNMPConfig
from app.services import snmp_monitor
from app.services.snmp_monitor import SNMPMonitor, IF_NAME


def _monitor():
    return SNMPMonitor(SNMPConfig(enabled=True, host="203.0.113.1", interface="if2"))


def _fake_transport():
    return SimpleNamespace(create=AsyncMock(return_value=object()))


async def test_walk_collects_flat_varbinds_until_leaving_tree():
    responses = [
        (None, 0, 0, ((f"{IF_NAME}.2", "eth0"),)),
        (None, 0, 0, ((f"{IF_NAME}.3", "eth1"),)),
        # Next OID is the sibling column (.2) outside the subtree -> walk must stop
        (None, 0, 0, (("1.3.6.1.2.1.31.1.1.1.2.2", "WAN"),)),
    ]
    with patch.object(snmp_monitor, "next_cmd", AsyncMock(side_effect=responses)), \
         patch.object(snmp_monitor, "UdpTransportTarget", _fake_transport()):
        results = await _monitor()._walk_oid(IF_NAME)

    assert results == [(f"{IF_NAME}.2", "eth0"), (f"{IF_NAME}.3", "eth1")]


async def test_walk_handles_multiple_varbinds_per_response():
    responses = [
        (None, 0, 0, ((f"{IF_NAME}.2", "eth0"), (f"{IF_NAME}.3", "eth1"))),
        (None, 0, 0, (("1.3.6.1.2.1.31.1.1.1.2.2", 7),)),
    ]
    with patch.object(snmp_monitor, "next_cmd", AsyncMock(side_effect=responses)), \
         patch.object(snmp_monitor, "UdpTransportTarget", _fake_transport()):
        results = await _monitor()._walk_oid(IF_NAME)

    assert results == [(f"{IF_NAME}.2", "eth0"), (f"{IF_NAME}.3", "eth1")]


async def test_walk_terminates_on_duplicate_oid():
    same = (None, 0, 0, ((f"{IF_NAME}.2", "eth0"),))
    with patch.object(snmp_monitor, "next_cmd", AsyncMock(side_effect=[same, same, same])), \
         patch.object(snmp_monitor, "UdpTransportTarget", _fake_transport()):
        results = await _monitor()._walk_oid(IF_NAME)

    assert results == [(f"{IF_NAME}.2", "eth0")]


async def test_walk_stops_on_error_indication():
    responses = [
        (None, 0, 0, ((f"{IF_NAME}.2", "eth0"),)),
        ("requestTimedOut", 0, 0, ()),
    ]
    with patch.object(snmp_monitor, "next_cmd", AsyncMock(side_effect=responses)), \
         patch.object(snmp_monitor, "UdpTransportTarget", _fake_transport()):
        results = await _monitor()._walk_oid(IF_NAME)

    assert results == [(f"{IF_NAME}.2", "eth0")]


def test_close_engine_is_safe_without_engine():
    mon = _monitor()
    mon._close_engine()  # engine never created; must not raise
    assert mon._snmp_engine is None
