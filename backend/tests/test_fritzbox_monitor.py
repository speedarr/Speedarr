"""FRITZ!Box WAN source (UPnP IGD GetAddonInfos) - parsing, rate and wiring.

The FRITZ!Box refreshes its 64-bit byte counters only every few seconds, so the
monitor reuses the SNMP sliding-window rate. These tests feed canned SOAP
responses (captured from a FRITZ!Box 6690 Cable, FRITZ!OS 8.x) instead of
talking to a real box.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.api import settings
from app.config import (
    REDACTED,
    BandwidthConfig,
    DownloadBandwidthConfig,
    SNMPConfig,
    SpeedarrConfig,
    StreamBandwidthConfig,
    UploadBandwidthConfig,
)
from app.services.config_manager import ConfigManager
from app.services import fritzbox_monitor
from app.services.fritzbox_monitor import (
    FritzBoxError,
    FritzBoxMonitor,
    extract_link_info,
    parse_soap_response,
)
from app.services.snmp_monitor import SNMPMonitor
from app.services.wan_monitor import create_wan_monitor


ADDON_INFOS_XML = """<?xml version="1.0"?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">
<s:Body>
<u:GetAddonInfosResponse xmlns:u="urn:schemas-upnp-org:service:WANCommonInterfaceConfig:1">
<NewByteSendRate>53399</NewByteSendRate>
<NewByteReceiveRate>1647192</NewByteReceiveRate>
<NewPacketSendRate>0</NewPacketSendRate>
<NewPacketReceiveRate>0</NewPacketReceiveRate>
<NewTotalBytesSent>3989925097</NewTotalBytesSent>
<NewTotalBytesReceived>2249862173</NewTotalBytesReceived>
<NewAutoDisconnectTime>0</NewAutoDisconnectTime>
<NewIdleDisconnectTime>0</NewIdleDisconnectTime>
<NewUpnpControlEnabled>1</NewUpnpControlEnabled>
<NewRoutedBridgedModeBoth>1</NewRoutedBridgedModeBoth>
<NewX_AVM_DE_TotalBytesSent64>2404876643561</NewX_AVM_DE_TotalBytesSent64>
<NewX_AVM_DE_TotalBytesReceived64>4413181275165</NewX_AVM_DE_TotalBytesReceived64>
<NewX_AVM_DE_WANAccessType>Cable</NewX_AVM_DE_WANAccessType>
<NewX_AVM_DE_Layer1UpstreamMaxBitRate64>86250000</NewX_AVM_DE_Layer1UpstreamMaxBitRate64>
<NewX_AVM_DE_Layer1DownstreamMaxBitRate64>1150000000</NewX_AVM_DE_Layer1DownstreamMaxBitRate64>
</u:GetAddonInfosResponse>
</s:Body>
</s:Envelope>"""

FAULT_XML = """<?xml version="1.0"?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
<s:Body><s:Fault><faultcode>s:Client</faultcode><faultstring>UPnPError</faultstring>
<detail><UPnPError xmlns="urn:schemas-upnp-org:control-1-0">
<errorCode>401</errorCode><errorDescription>Invalid Action</errorDescription>
</UPnPError></detail></s:Fault></s:Body></s:Envelope>"""


def _config(**overrides):
    values = dict(enabled=True, source="fritzbox", host="192.168.178.1", port=49000)
    values.update(overrides)
    return SNMPConfig(**values)


def _infos(rx, tx, **extra):
    infos = {
        "NewX_AVM_DE_TotalBytesReceived64": str(rx),
        "NewX_AVM_DE_TotalBytesSent64": str(tx),
        "NewByteReceiveRate": "0",
        "NewByteSendRate": "0",
    }
    infos.update(extra)
    return infos


class _ScriptedBox:
    """Feeds a sequence of (time, GetAddonInfos dict) to a FritzBoxMonitor."""

    def __init__(self, monitor, readings):
        self.readings = list(readings)
        self.now = 0.0
        monitor.get_addon_infos = self._get_addon_infos

    async def _get_addon_infos(self):
        self.now, infos = self.readings.pop(0)
        return infos

    def time(self):
        return self.now


async def _run(monitor, readings):
    box = _ScriptedBox(monitor, readings)
    results = []
    with patch.object(fritzbox_monitor.time, "time", box.time):
        for _ in range(len(box.readings)):
            results.append(await monitor.get_bandwidth())
    return results


# --- SOAP parsing -----------------------------------------------------------

def test_parse_addon_infos_strips_namespaces():
    fields = parse_soap_response(ADDON_INFOS_XML, "GetAddonInfos")
    assert fields["NewX_AVM_DE_TotalBytesReceived64"] == "4413181275165"
    assert fields["NewByteSendRate"] == "53399"


def test_parse_soap_fault_raises_with_upnp_code():
    with pytest.raises(FritzBoxError, match="401: Invalid Action"):
        parse_soap_response(FAULT_XML, "GetAddonInfos")


def test_parse_rejects_garbage_and_wrong_action():
    with pytest.raises(FritzBoxError):
        parse_soap_response("<html>not soap", "GetAddonInfos")
    with pytest.raises(FritzBoxError, match="No GetCommonLinkPropertiesResponse"):
        parse_soap_response(ADDON_INFOS_XML, "GetCommonLinkProperties")


def test_extract_link_info_reports_line_speed_in_mbps():
    info = extract_link_info(parse_soap_response(ADDON_INFOS_XML, "GetAddonInfos"))
    assert info == {"access_type": "Cable", "downstream_mbps": 1150.0, "upstream_mbps": 86.25}
    assert extract_link_info({}) is None


# --- rate calculation -------------------------------------------------------

async def test_first_poll_is_baseline_then_windowed_rate():
    # 10 Mbps down (1.25 MB/s), 2 Mbps up (0.25 MB/s), counters stepping every 3s
    # like the real box: reads at 1s spacing see repeated values.
    rx0, tx0 = 4_413_000_000_000, 2_404_000_000_000
    readings = []
    for t in range(0, 31):
        step = 3 * (t // 3)
        readings.append((float(t), _infos(rx0 + 1_250_000 * step, tx0 + 250_000 * step)))
    results = await _run(FritzBoxMonitor(_config()), readings)

    assert results[0] is None  # baseline
    final = results[-1]
    assert abs(final["download"] - 10.0) < 0.5
    assert abs(final["upload"] - 2.0) < 0.2


async def test_counter_reset_restarts_window_instead_of_spiking():
    readings = [
        (0.0, _infos(5_000_000_000, 1_000_000_000)),
        (5.0, _infos(5_006_250_000, 1_001_250_000)),  # 10 / 2 Mbps
        (10.0, _infos(1_000, 500)),  # box rebooted: counters start over
        (15.0, _infos(6_251_000, 1_250_500)),  # 10 / 2 Mbps again
    ]
    results = await _run(FritzBoxMonitor(_config()), readings)

    assert results[0] is None
    assert results[1] == {"download": 10.0, "upload": 2.0}
    assert results[2] is None  # fresh baseline, no 2**64 wrap spike
    assert results[3] == {"download": 10.0, "upload": 2.0}


async def test_counter_jitter_does_not_reset_window_or_go_negative():
    """Real FRITZ!Box counters step back by a few MB between refreshes (seen
    live: -1.1 MB, -3.4 MB, -12 kB). That must neither restart the window nor
    yield a negative / wrapped rate."""
    base = 4_413_000_000_000
    readings = [
        (0.0, _infos(base, 1_000_000)),
        (5.0, _infos(base + 6_250_000, 2_250_000)),  # 10 / 2 Mbps
        (10.0, _infos(base + 2_875_000, 3_500_000)),  # rx dips 3.4 MB
        (15.0, _infos(base + 18_750_000, 4_750_000)),  # caught up: 10 / 2 Mbps overall
    ]
    monitor = FritzBoxMonitor(_config())
    results = await _run(monitor, readings)

    assert results[0] is None
    assert results[1] == {"download": 10.0, "upload": 2.0}
    # During the dip the held value keeps the rate non-negative and the window intact.
    assert results[2] is not None and results[2]["download"] >= 0
    assert results[3] == {"download": 10.0, "upload": 2.0}
    assert len(monitor._samples) == 4


def test_is_counter_reset_separates_reboot_from_jitter():
    assert fritzbox_monitor.is_counter_reset(4_413_000_000_000, 12_345)
    assert not fritzbox_monitor.is_counter_reset(4_413_376_592_539, 4_413_373_216_046)
    assert not fritzbox_monitor.is_counter_reset(100, 100)


async def test_falls_back_to_byte_rates_without_64bit_counters():
    infos = {"NewByteReceiveRate": "1250000", "NewByteSendRate": "250000"}
    results = await _run(FritzBoxMonitor(_config()), [(0.0, infos)])
    assert results == [{"download": 10.0, "upload": 2.0}]


async def test_query_failure_returns_none_and_clears_window():
    monitor = FritzBoxMonitor(_config())
    monitor._samples.append((0.0, 1, 1))

    async def boom():
        raise FritzBoxError("HTTP 404")

    monitor.get_addon_infos = boom
    assert await monitor.get_bandwidth() is None
    assert not monitor._samples


async def test_disabled_or_hostless_config_is_inert():
    assert await FritzBoxMonitor(_config(enabled=False)).get_bandwidth() is None
    assert await FritzBoxMonitor(_config(host="")).get_bandwidth() is None


# --- wiring -----------------------------------------------------------------

def test_factory_selects_monitor_by_source():
    assert isinstance(create_wan_monitor(_config()), FritzBoxMonitor)
    assert isinstance(create_wan_monitor(SNMPConfig(enabled=True, host="10.0.0.1")), SNMPMonitor)


def test_source_defaults_to_snmp_for_existing_configs():
    assert SNMPConfig().source == "snmp"
    with pytest.raises(ValueError):
        SNMPConfig(source="carrier-pigeon")


async def test_switching_to_fritzbox_saves_once_the_community_is_cleared(db):
    """The UI clears the (hidden) community string when switching to the FRITZ!Box: a stored
    secret may not stay beside the changed host/port (audit NEW-5), a cleared one may."""
    state = SimpleNamespace(config=None, polling_monitor=None, decision_engine=None,
                            controller_manager=None, notification_service=None)
    manager = ConfigManager(app=SimpleNamespace(state=state))
    await manager.migrate_yaml_to_db(SpeedarrConfig(bandwidth=BandwidthConfig(
        download=DownloadBandwidthConfig(total_limit=100.0),
        upload=UploadBandwidthConfig(total_limit=50.0),
        streams=StreamBandwidthConfig(),
    )), db)
    state.config = await manager.load_config_from_db(db)
    manager._reload_services = AsyncMock()

    switch = {"enabled": True, "source": "fritzbox", "host": "192.168.178.1", "port": 49000}
    with pytest.raises(ValueError, match="enter the community string"):
        await manager.update_section("snmp", {**switch, "community": REDACTED}, db)

    cfg = await manager.update_section("snmp", {**switch, "community": ""}, db)
    assert cfg.snmp.source == "fritzbox"
    assert cfg.snmp.port == 49000


async def test_settings_test_connection_reports_line_speed():
    test_request = settings.TestConnectionRequest(
        config=_config().model_dump(), use_existing=False
    )
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(config=None)))

    async def fake_call(self, action):
        return parse_soap_response(ADDON_INFOS_XML, action)

    with patch.object(FritzBoxMonitor, "_call", fake_call):
        resp = await settings.test_connection("snmp", test_request, request, current_user=None)

    assert resp.success is True
    assert "FRITZ!Box" in resp.message
    assert "1150 Mbps down / 86.25 Mbps up" in resp.message
    assert resp.details["link"]["access_type"] == "Cable"


async def test_settings_test_connection_explains_upnp_setting_on_failure():
    test_request = settings.TestConnectionRequest(
        config=_config().model_dump(), use_existing=False
    )
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(config=None)))

    async def fake_call(self, action):
        raise FritzBoxError("HTTP 404")

    with patch.object(FritzBoxMonitor, "_call", fake_call):
        resp = await settings.test_connection("snmp", test_request, request, current_user=None)

    assert resp.success is False
    assert "Transmit status information over UPnP" in resp.message
