"""
FRITZ!Box WAN monitoring via UPnP IGD (TR-064 style SOAP, no login required).

AVM FRITZ!Box routers do not offer SNMP on the LAN side, but they publish the
WAN byte counters through the UPnP Internet Gateway Device service once
"Transmit status information over UPnP" is enabled (Home Network > Network >
Network Settings). This monitor reads those counters and turns them into the
same ``{"download": Mbps, "upload": Mbps}`` shape the SNMP monitor produces,
so the decision engine, metrics and dashboard treat both sources identically.
"""
import time
import xml.etree.ElementTree as ET
from collections import deque
from typing import Deque, Dict, Optional, Tuple

import aiohttp
from loguru import logger

from app.config import SNMPConfig
from app.services.snmp_monitor import RATE_WINDOW_SECONDS, compute_windowed_rate

# The IGD control endpoint the FRITZ!Box serves without authentication.
CONTROL_PATH = "/igdupnp/control/WANCommonIFC1"
SERVICE_TYPE = "urn:schemas-upnp-org:service:WANCommonInterfaceConfig:1"
DEFAULT_PORT = 49000
REQUEST_TIMEOUT_SECONDS = 3.0

# Same ceiling the SNMP monitor uses to reject nonsense readings.
MAX_REASONABLE_MBPS = 10000  # 10 Gbps

_SOAP_ENVELOPE = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
    's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">'
    '<s:Body><u:{action} xmlns:u="{service}"/></s:Body>'
    "</s:Envelope>"
)


class FritzBoxError(Exception):
    """Raised when the FRITZ!Box returns a SOAP fault or an unusable response."""


def parse_soap_response(xml_text: str, action: str) -> Dict[str, str]:
    """Return the ``<action>Response`` children as a flat ``{tag: text}`` dict.

    Namespaces are stripped from tag names. A SOAP fault (e.g. UPnP error 401
    "Invalid Action" on boxes that lack the AVM extensions) raises
    ``FritzBoxError`` with the UPnP error code and description.
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        raise FritzBoxError(f"Invalid SOAP response: {e}") from e

    def local(tag: str) -> str:
        return tag.rsplit("}", 1)[-1]

    for elem in root.iter():
        name = local(elem.tag)
        if name == "Fault":
            fields = {local(e.tag): (e.text or "").strip() for e in elem.iter()}
            code = fields.get("errorCode", "?")
            desc = fields.get("errorDescription") or fields.get("faultstring", "SOAP fault")
            raise FritzBoxError(f"UPnP error {code}: {desc}")
        if name == f"{action}Response":
            return {local(child.tag): (child.text or "").strip() for child in elem}

    raise FritzBoxError(f"No {action}Response element in SOAP response")


def _int_or_none(value: Optional[str]) -> Optional[int]:
    try:
        return int(value) if value not in (None, "") else None
    except ValueError:
        return None


def is_counter_reset(previous: int, current: int) -> bool:
    """True when a byte counter dropped far enough to mean a reset, not jitter.

    Observed on a FRITZ!Box 6690 (FRITZ!OS 8.x): the 64-bit totals step back
    by up to a few MB every minute or so and recover on the next refresh. A
    reboot or reconnect instead drops the counter to (near) zero. Falling below
    half of the previous value separates the two at any counter size.
    """
    return current < previous // 2


def extract_link_info(addon_infos: Dict[str, str]) -> Optional[Dict[str, object]]:
    """Physical line speed (Mbps) from a GetAddonInfos response, if present.

    The FRITZ!Box reports the synced line rate (e.g. DOCSIS/DSL profile), which
    is a good starting point for the total bandwidth limits.
    """
    down = _int_or_none(addon_infos.get("NewX_AVM_DE_Layer1DownstreamMaxBitRate64"))
    up = _int_or_none(addon_infos.get("NewX_AVM_DE_Layer1UpstreamMaxBitRate64"))
    if not down or not up:
        return None
    return {
        "access_type": addon_infos.get("NewX_AVM_DE_WANAccessType") or None,
        "downstream_mbps": round(down / 1_000_000, 2),
        "upstream_mbps": round(up / 1_000_000, 2),
    }


class FritzBoxMonitor:
    """
    Monitors WAN bandwidth of an AVM FRITZ!Box via UPnP IGD ``GetAddonInfos``.

    Uses the 64-bit ``NewX_AVM_DE_TotalBytes{Received,Sent}64`` counters with the
    same sliding-window averaging as the SNMP monitor: the box only refreshes
    those counters every few seconds, so two-point differencing would alias.
    Falls back to the box's own ``NewByte{Receive,Send}Rate`` (bytes/s) when the
    64-bit counters are not provided.
    """

    def __init__(self, config: SNMPConfig):
        self.config = config
        # Sliding window of (timestamp, rx_bytes, tx_bytes), see compute_windowed_rate.
        self._samples: Deque[Tuple[float, int, int]] = deque()

    @property
    def _url(self) -> str:
        port = self.config.port or DEFAULT_PORT
        return f"http://{self.config.host}:{port}{CONTROL_PATH}"

    async def _call(self, action: str) -> Dict[str, str]:
        """POST a parameterless SOAP action and return its response fields."""
        headers = {
            "Content-Type": 'text/xml; charset="utf-8"',
            "SOAPAction": f'"{SERVICE_TYPE}#{action}"',
        }
        body = _SOAP_ENVELOPE.format(action=action, service=SERVICE_TYPE)
        timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(self._url, data=body, headers=headers) as response:
                text = await response.text()
                # SOAP faults come back as HTTP 500 with a Fault body; let the
                # parser turn those into a readable error.
                if response.status != 200 and "Fault" not in text:
                    raise FritzBoxError(f"HTTP {response.status} from {self._url}")
                return parse_soap_response(text, action)

    async def get_addon_infos(self) -> Dict[str, str]:
        return await self._call("GetAddonInfos")

    async def get_link_info(self) -> Optional[Dict[str, object]]:
        """Line speed in Mbps, from GetAddonInfos or GetCommonLinkProperties."""
        info = extract_link_info(await self.get_addon_infos())
        if info:
            return info
        props = await self._call("GetCommonLinkProperties")
        down = _int_or_none(props.get("NewLayer1DownstreamMaxBitRate"))
        up = _int_or_none(props.get("NewLayer1UpstreamMaxBitRate"))
        if not down or not up:
            return None
        return {
            "access_type": props.get("NewWANAccessType") or None,
            "downstream_mbps": round(down / 1_000_000, 2),
            "upstream_mbps": round(up / 1_000_000, 2),
        }

    async def get_bandwidth(self) -> Optional[Dict[str, float]]:
        """
        Get current WAN bandwidth usage from the FRITZ!Box.

        Returns:
            Dict with 'download' and 'upload' in Mbps, or None if unavailable
            (disabled, first sample, or query failed).
        """
        if not self.config.enabled or not self.config.host:
            return None

        try:
            infos = await self.get_addon_infos()
        except Exception as e:
            logger.warning(f"FRITZ!Box query failed: {e}")
            self._samples.clear()
            return None

        rx = _int_or_none(infos.get("NewX_AVM_DE_TotalBytesReceived64"))
        tx = _int_or_none(infos.get("NewX_AVM_DE_TotalBytesSent64"))

        if rx is None or tx is None:
            # Older firmware without the 64-bit counters: use the box's own
            # (smoothed, ~5s) byte rates directly.
            rx_rate = _int_or_none(infos.get("NewByteReceiveRate"))
            tx_rate = _int_or_none(infos.get("NewByteSendRate"))
            if rx_rate is None or tx_rate is None:
                logger.warning("FRITZ!Box response has neither byte counters nor byte rates")
                return None
            download_mbps = rx_rate * 8 / 1_000_000
            upload_mbps = tx_rate * 8 / 1_000_000
            logger.debug(f"FRITZ!Box (rate fallback): {download_mbps:.2f} Mbps down, {upload_mbps:.2f} Mbps up")
            return {"download": round(download_mbps, 2), "upload": round(upload_mbps, 2)}

        current_time = time.time()

        if self._samples:
            last_rx, last_tx = self._samples[-1][1], self._samples[-1][2]
            if is_counter_reset(last_rx, rx) or is_counter_reset(last_tx, tx):
                # Reboot or counter reset (e.g. reconnect): start a fresh window
                # instead of letting the wrap math produce a huge bogus rate.
                logger.info("FRITZ!Box counters reset (reboot or reconnect?) - resetting window")
                self._samples.clear()
            else:
                # The box's counters are not strictly monotonic: they regularly
                # step back by a few MB and catch up on the next refresh. Hold the
                # previous value through such a dip so the window delta stays exact.
                rx = max(rx, last_rx)
                tx = max(tx, last_tx)

        self._samples.append((current_time, rx, tx))
        cutoff = current_time - RATE_WINDOW_SECONDS
        while len(self._samples) > 2 and self._samples[0][0] < cutoff:
            self._samples.popleft()

        if len(self._samples) < 2:
            logger.debug("FRITZ!Box baseline established")
            return None

        rate = compute_windowed_rate(list(self._samples), use_64bit=True)
        if rate is None:
            logger.debug("FRITZ!Box window span too short for a rate")
            return None
        download_mbps, upload_mbps = rate

        if download_mbps > MAX_REASONABLE_MBPS or upload_mbps > MAX_REASONABLE_MBPS:
            logger.warning(
                f"FRITZ!Box: Rejecting unreasonable values - {download_mbps:.2f} Mbps down, "
                f"{upload_mbps:.2f} Mbps up. Resetting window."
            )
            latest = self._samples[-1]
            self._samples.clear()
            self._samples.append(latest)
            return None

        logger.debug(f"FRITZ!Box: {download_mbps:.2f} Mbps down, {upload_mbps:.2f} Mbps up")
        return {"download": round(download_mbps, 2), "upload": round(upload_mbps, 2)}

    async def test_connection(self) -> bool:
        """Check that GetAddonInfos answers with usable traffic data."""
        try:
            infos = await self.get_addon_infos()
        except Exception as e:
            logger.error(f"FRITZ!Box connection test failed: {e}")
            return False
        has_data = (
            "NewX_AVM_DE_TotalBytesReceived64" in infos or "NewByteReceiveRate" in infos
        )
        if not has_data:
            logger.error("FRITZ!Box connection test: response contains no traffic data")
        return has_data

    async def close(self):
        """Nothing to release - every request uses its own short-lived session."""
        logger.debug("FRITZ!Box monitor closed")
