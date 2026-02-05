"""
SNMP monitoring service for network-wide bandwidth tracking.
"""
import asyncio
import time
from typing import Dict, Optional, List, Tuple
from loguru import logger
from pysnmp.hlapi.asyncio import (
    SnmpEngine,
    CommunityData,
    UdpTransportTarget,
    ContextData,
    ObjectType,
    ObjectIdentity,
    getCmd,
    nextCmd,
)
from pyasn1.type.univ import Integer, OctetString
from pysnmp.proto.rfc1902 import Gauge32, Counter32, Counter64, Integer32, Unsigned32

from app.config import SNMPConfig


# Standard MIB-II OIDs
IF_INDEX = "1.3.6.1.2.1.2.2.1.1"  # ifIndex
IF_DESCR = "1.3.6.1.2.1.2.2.1.2"  # ifDescr (technical name)
IF_TYPE = "1.3.6.1.2.1.2.2.1.3"  # ifType
IF_SPEED = "1.3.6.1.2.1.2.2.1.5"  # ifSpeed (in bits/sec)
IF_ADMIN_STATUS = "1.3.6.1.2.1.2.2.1.7"  # ifAdminStatus (1=up, 2=down)
IF_OPER_STATUS = "1.3.6.1.2.1.2.2.1.8"  # ifOperStatus (1=up, 2=down)

# IF-MIB extended OIDs
IF_NAME = "1.3.6.1.2.1.31.1.1.1.1"  # ifName (short name like "eth0")
IF_HIGH_SPEED = "1.3.6.1.2.1.31.1.1.1.15"  # ifHighSpeed (speed in Mbps for high-speed interfaces)
IF_ALIAS = "1.3.6.1.2.1.31.1.1.1.18"  # ifAlias (user-configurable description)

# 64-bit counters (for high-speed interfaces)
IF_HC_IN_OCTETS = "1.3.6.1.2.1.31.1.1.1.6"  # ifHCInOctets
IF_HC_OUT_OCTETS = "1.3.6.1.2.1.31.1.1.1.10"  # ifHCOutOctets

# 32-bit counters (fallback for older devices)
IF_IN_OCTETS = "1.3.6.1.2.1.2.2.1.10"  # ifInOctets
IF_OUT_OCTETS = "1.3.6.1.2.1.2.2.1.16"  # ifOutOctets


class NetworkInterface:
    """Represents a network interface discovered via SNMP."""

    def __init__(
        self,
        index: int,
        name: str,
        description: str,
        type_id: int,
        speed: int,
        admin_status: int,
        oper_status: int,
        in_octets: int = 0,
        out_octets: int = 0,
        current_in_mbps: float = 0.0,
        current_out_mbps: float = 0.0,
    ):
        self.index = index
        self.name = name
        self.description = description
        self.type_id = type_id
        self.speed = speed  # Mbps
        self.admin_status = admin_status
        self.oper_status = oper_status
        self.in_octets = in_octets  # Total bytes received
        self.out_octets = out_octets  # Total bytes sent
        self.current_in_mbps = current_in_mbps  # Current download speed at time of scan
        self.current_out_mbps = current_out_mbps  # Current upload speed at time of scan

    @property
    def status(self) -> str:
        """Get interface status as string."""
        return "up" if self.oper_status == 1 else "down"

    @property
    def is_up(self) -> bool:
        """Check if interface is operational."""
        return self.oper_status == 1

    @property
    def type_name(self) -> str:
        """Get interface type name."""
        # Common interface types
        types = {
            6: "ethernet",
            24: "loopback",
            131: "tunnel",
            136: "l2vlan",
        }
        return types.get(self.type_id, "other")

    def to_dict(self) -> dict:
        """Convert to dictionary for API response."""
        # Format traffic for display (in GB)
        in_gb = self.in_octets / (1024 ** 3) if self.in_octets else 0
        out_gb = self.out_octets / (1024 ** 3) if self.out_octets else 0

        return {
            "index": self.index,
            "name": self.name,
            "description": self.description,
            "type": self.type_name,
            "speed": self.speed,
            "status": self.status,
            "is_wan_candidate": False,  # Will be set by suggest_wan_interface
            "in_gb": round(in_gb, 2),
            "out_gb": round(out_gb, 2),
            "in_octets": self.in_octets,
            "out_octets": self.out_octets,
            "current_in_mbps": round(self.current_in_mbps, 2),
            "current_out_mbps": round(self.current_out_mbps, 2),
        }


class SNMPMonitor:
    """
    Monitors router/switch bandwidth via SNMP v2c.
    """

    def __init__(self, config: SNMPConfig):
        self.config = config
        self._last_in_octets: Optional[int] = None
        self._last_out_octets: Optional[int] = None
        self._last_poll_time: Optional[float] = None
        self._use_64bit = True  # Try 64-bit counters first
        self._snmp_engine: Optional[SnmpEngine] = None

    def _get_engine(self) -> SnmpEngine:
        """Get or create a shared SNMP engine instance."""
        if self._snmp_engine is None:
            self._snmp_engine = SnmpEngine()
        return self._snmp_engine

    def _close_engine(self):
        """Close and dispose of the SNMP engine to free memory."""
        if self._snmp_engine is not None:
            try:
                self._snmp_engine.transportDispatcher.closeDispatcher()
            except Exception as e:
                logger.debug(f"Error closing SNMP dispatcher: {e}")
            self._snmp_engine = None

    def _get_auth_data(self) -> CommunityData:
        """Build pysnmp authentication data for SNMPv2c."""
        return CommunityData(self.config.community, mpModel=1)

    async def _get_oid(self, oid: str, interface_index: str) -> Optional[int]:
        """Query a single SNMP OID value."""
        try:
            auth_data = self._get_auth_data()
            target = UdpTransportTarget(
                (self.config.host, self.config.port), timeout=2.0, retries=1
            )

            # Extract numeric index from interface_index (handles both "5" and "if5")
            if interface_index.startswith("if"):
                numeric_index = interface_index[2:]  # Remove "if" prefix
            else:
                numeric_index = interface_index

            # Append interface index to OID
            full_oid = f"{oid}.{numeric_index}"

            errorIndication, errorStatus, errorIndex, varBinds = await getCmd(
                self._get_engine(),
                auth_data,
                target,
                ContextData(),
                ObjectType(ObjectIdentity(full_oid)),
            )

            if errorIndication:
                logger.error(f"SNMP error indication: {errorIndication}")
                return None
            elif errorStatus:
                logger.error(
                    f"SNMP error status: {errorStatus.prettyPrint()} at {errorIndex and varBinds[int(errorIndex) - 1][0] or '?'}"
                )
                return None
            else:
                # Extract value from varBinds
                for varBind in varBinds:
                    value = varBind[1]
                    # Handle all numeric SNMP types
                    if isinstance(value, (Integer, Integer32, Gauge32, Counter32, Counter64, Unsigned32)):
                        return int(value)
                    # Try to convert any value that looks numeric
                    try:
                        return int(value)
                    except (ValueError, TypeError):
                        pass
                return None

        except Exception as e:
            logger.error(f"SNMP query error for OID {oid}: {e}")
            return None

    async def _get_multiple_oids(self, oids: List[str], interface_index: str) -> Dict[str, Optional[int]]:
        """
        Query multiple SNMP OIDs in a single request for cache consistency.

        This ensures all OID values come from the same device cache snapshot,
        avoiding inconsistencies that can occur with separate requests.
        """
        results = {oid: None for oid in oids}

        try:
            auth_data = self._get_auth_data()
            target = UdpTransportTarget(
                (self.config.host, self.config.port), timeout=2.0, retries=1
            )

            # Extract numeric index from interface_index
            if interface_index.startswith("if"):
                numeric_index = interface_index[2:]
            else:
                numeric_index = interface_index

            # Build ObjectType list for all OIDs
            object_types = [
                ObjectType(ObjectIdentity(f"{oid}.{numeric_index}"))
                for oid in oids
            ]

            # Single SNMP GET request for all OIDs
            errorIndication, errorStatus, errorIndex, varBinds = await getCmd(
                self._get_engine(),
                auth_data,
                target,
                ContextData(),
                *object_types,  # Unpack all ObjectTypes as separate arguments
            )

            if errorIndication:
                logger.error(f"SNMP bulk query error indication: {errorIndication}")
                return results
            elif errorStatus:
                logger.error(
                    f"SNMP bulk query error status: {errorStatus.prettyPrint()}"
                )
                return results
            else:
                # Extract values from varBinds - matches order of input OIDs
                for i, varBind in enumerate(varBinds):
                    if i < len(oids):
                        value = varBind[1]
                        # Handle all numeric SNMP types
                        if isinstance(value, (Integer, Integer32, Gauge32, Counter32, Counter64, Unsigned32)):
                            results[oids[i]] = int(value)
                        else:
                            try:
                                results[oids[i]] = int(value)
                            except (ValueError, TypeError):
                                pass

            return results

        except Exception as e:
            logger.error(f"SNMP bulk query error: {e}")
            return results

    async def _walk_oid(self, oid: str) -> List[Tuple[str, any]]:
        """Walk an SNMP OID tree and return all sub-OIDs and values."""
        try:
            auth_data = self._get_auth_data()
            target = UdpTransportTarget(
                (self.config.host, self.config.port), timeout=5.0, retries=2
            )

            results = []
            # Use getNextCmd for walking (more reliable than bulkCmd)
            start_oid = ObjectType(ObjectIdentity(oid))

            # Track last OID to prevent infinite loops
            last_oid = None
            max_iterations = 1000

            for iteration in range(max_iterations):
                errorIndication, errorStatus, errorIndex, varBinds = await nextCmd(
                    self._get_engine(),
                    auth_data,
                    target,
                    ContextData(),
                    start_oid,
                )

                if errorIndication:
                    logger.debug(f"SNMP walk stopped: {errorIndication}")
                    break
                elif errorStatus:
                    logger.debug(f"SNMP walk status: {errorStatus.prettyPrint()}")
                    break

                if not varBinds or len(varBinds) == 0:
                    logger.debug("Walk complete, no more varBinds")
                    break

                # varBinds is [[ObjectType(...)]] - a list containing a list of ObjectType
                # Each varBindTable is [ObjectType(...)] - a list with ObjectType items
                for varBindTable in varBinds:
                    for varBind in varBindTable:
                        # Now varBind is the actual ObjectType
                        name = varBind[0]
                        value = varBind[1]

                        current_oid = str(name)

                        logger.debug(f"Walk iteration {iteration}: OID={current_oid}, value={value}")

                        # Check if we've left the requested OID tree
                        if not current_oid.startswith(oid):
                            logger.debug(f"Walk complete, left OID tree at {current_oid}. Got {len(results)} results")
                            return results

                        # Check for duplicate (infinite loop protection)
                        if current_oid == last_oid:
                            logger.debug(f"Walk complete, duplicate OID detected: {current_oid}")
                            return results

                        results.append((current_oid, value))
                        last_oid = current_oid
                        start_oid = ObjectType(ObjectIdentity(current_oid))

            logger.debug(f"Walk completed with {len(results)} results")
            return results

        except Exception as e:
            logger.error(f"SNMP walk error for OID {oid}: {e}")
            return []

    async def get_bandwidth(self) -> Optional[Dict[str, float]]:
        """
        Get current bandwidth usage from SNMP device.

        Uses bulk SNMP query to get both counters in single request,
        ensuring cache consistency and avoiding doubled readings.

        Returns:
            Dict with 'download' and 'upload' in Mbps, or None if unavailable
        """
        if not self.config.enabled or not self.config.interface:
            return None

        try:
            # Determine which OID set to use (64-bit or 32-bit)
            in_oid = IF_HC_IN_OCTETS if self._use_64bit else IF_IN_OCTETS
            out_oid = IF_HC_OUT_OCTETS if self._use_64bit else IF_OUT_OCTETS

            # Query BOTH counters in a single request for cache consistency
            # This ensures both values come from the same device cache snapshot
            results = await self._get_multiple_oids([in_oid, out_oid], self.config.interface)
            in_octets = results.get(in_oid)
            out_octets = results.get(out_oid)

            # If 64-bit counters fail, fall back to 32-bit
            if in_octets is None and self._use_64bit:
                logger.info("64-bit counters unavailable, falling back to 32-bit")
                self._use_64bit = False
                # Reset baseline to avoid incorrect delta between different counter types
                self._last_in_octets = None
                self._last_out_octets = None
                self._last_poll_time = None
                in_oid = IF_IN_OCTETS
                out_oid = IF_OUT_OCTETS
                results = await self._get_multiple_oids([in_oid, out_oid], self.config.interface)
                in_octets = results.get(in_oid)
                out_octets = results.get(out_oid)

            if in_octets is None or out_octets is None:
                logger.warning("Failed to query SNMP bandwidth counters")
                # Clear baseline so recovery establishes a fresh one
                self._last_in_octets = None
                self._last_out_octets = None
                self._last_poll_time = None
                return None

            current_time = time.time()

            # First poll - establish baseline
            if self._last_in_octets is None or self._last_poll_time is None:
                self._last_in_octets = in_octets
                self._last_out_octets = out_octets
                self._last_poll_time = current_time
                logger.debug("SNMP baseline established")
                return None

            # Calculate time delta
            time_diff = current_time - self._last_poll_time
            if time_diff < 0.1:
                logger.warning("SNMP poll interval too short")
                return None

            # Calculate byte deltas
            in_delta = in_octets - self._last_in_octets
            out_delta = out_octets - self._last_out_octets

            # Handle counter wrap-around (32-bit or 64-bit)
            max_counter = 2**64 if self._use_64bit else 2**32
            if in_delta < 0:
                in_delta += max_counter
            if out_delta < 0:
                out_delta += max_counter

            # Convert to Mbps: (bytes/sec * 8 bits/byte) / 1,000,000
            download_mbps = (in_delta / time_diff) * 8 / 1_000_000
            upload_mbps = (out_delta / time_diff) * 8 / 1_000_000

            # Sanity check: reject negative or unreasonably high values (> 10 Gbps)
            # This catches counter wrap-around issues, counter type switching, or calculation errors
            MAX_REASONABLE_MBPS = 10000  # 10 Gbps
            if download_mbps < 0 or upload_mbps < 0 or download_mbps > MAX_REASONABLE_MBPS or upload_mbps > MAX_REASONABLE_MBPS:
                logger.warning(
                    f"SNMP: Rejecting unreasonable values - {download_mbps:.2f} Mbps down, {upload_mbps:.2f} Mbps up "
                    f"(in_delta={in_delta}, out_delta={out_delta}, time_diff={time_diff:.2f}s). "
                    f"Resetting baseline."
                )
                self._last_in_octets = in_octets
                self._last_out_octets = out_octets
                self._last_poll_time = current_time
                return None

            # Update last values
            self._last_in_octets = in_octets
            self._last_out_octets = out_octets
            self._last_poll_time = current_time

            logger.debug(f"SNMP: {download_mbps:.2f} Mbps down, {upload_mbps:.2f} Mbps up")

            return {
                "download": round(download_mbps, 2),
                "upload": round(upload_mbps, 2),
            }

        except Exception as e:
            logger.error(f"SNMP bandwidth monitoring error: {e}")
            # Clear baseline so recovery establishes a fresh one
            self._last_in_octets = None
            self._last_out_octets = None
            self._last_poll_time = None
            return None

    async def test_connection(self) -> bool:
        """
        Test SNMP connection to device.

        Returns:
            True if connection successful, False otherwise
        """
        try:
            auth_data = self._get_auth_data()
            target = UdpTransportTarget(
                (self.config.host, self.config.port), timeout=2.0, retries=1
            )

            # Try to query sysDescr (1.3.6.1.2.1.1.1.0) - universal OID
            errorIndication, errorStatus, errorIndex, varBinds = await getCmd(
                self._get_engine(),
                auth_data,
                target,
                ContextData(),
                ObjectType(ObjectIdentity("1.3.6.1.2.1.1.1.0")),
            )

            if errorIndication:
                logger.error(f"SNMP connection test failed: {errorIndication}")
                return False
            elif errorStatus:
                logger.error(f"SNMP connection test error: {errorStatus.prettyPrint()}")
                return False
            else:
                logger.info("SNMP connection test successful")
                return True

        except Exception as e:
            logger.error(f"SNMP connection test exception: {e}")
            return False

    def _should_skip_interface(self, name: str) -> bool:
        """
        Check if an interface should be skipped based on naming patterns.

        Skips: VLAN interfaces (.), switch ports, bridges, loopback, dummy, tunnels, etc.
        """
        name_lower = name.lower()

        # Skip VLAN sub-interfaces (contain a dot like eth5.20)
        if "." in name:
            return True

        # Skip specific interface types by keyword
        skip_keywords = ["switch", "br", "lo", "dummy", "miireg", "bond", "tun", "ifb"]
        for keyword in skip_keywords:
            if keyword in name_lower:
                return True

        return False

    async def discover_interfaces(self) -> List[NetworkInterface]:
        """
        Discover all network interfaces on the SNMP device.

        Returns:
            List of NetworkInterface objects
        """
        interfaces = []

        try:
            # First, walk interface names to filter early
            name_walk = await self._walk_oid(IF_NAME)
            if not name_walk:
                # Fall back to ifDescr if ifName not available
                name_walk = await self._walk_oid(IF_DESCR)

            if not name_walk:
                logger.warning("No interfaces discovered via SNMP")
                return []

            # Build map of index -> name and filter out irrelevant interfaces
            all_interfaces: Dict[int, str] = {}
            for oid_str, value in name_walk:
                index = int(oid_str.split(".")[-1])
                try:
                    if isinstance(value, OctetString):
                        name = str(value).strip()
                    elif hasattr(value, 'prettyPrint'):
                        name = value.prettyPrint().strip()
                    else:
                        name = str(value).strip()
                    all_interfaces[index] = name
                except (ValueError, TypeError):
                    all_interfaces[index] = f"if{index}"

            # Filter interfaces - skip VLANs, bridges, loopback, etc.
            interface_indices = []
            skipped_count = 0
            for index, name in all_interfaces.items():
                if self._should_skip_interface(name):
                    logger.debug(f"Skipping interface {index}: {name}")
                    skipped_count += 1
                else:
                    interface_indices.append(index)

            logger.info(f"Discovered {len(all_interfaces)} interfaces, querying {len(interface_indices)} (skipped {skipped_count} VLANs/bridges/internal)")

            if not interface_indices:
                logger.warning("No relevant interfaces found after filtering")
                return []

            # First pass: Get baseline traffic counters for speed calculation
            # Use bulk queries for each interface to ensure cache consistency
            baseline_time = time.time()
            baseline_in: Dict[int, int] = {}
            baseline_out: Dict[int, int] = {}

            for idx in interface_indices:
                results = await self._get_multiple_oids([IF_HC_IN_OCTETS, IF_HC_OUT_OCTETS], str(idx))
                in_val = results.get(IF_HC_IN_OCTETS)
                out_val = results.get(IF_HC_OUT_OCTETS)
                if in_val is not None:
                    baseline_in[idx] = int(in_val)
                if out_val is not None:
                    baseline_out[idx] = int(out_val)

            logger.debug(f"Baseline counters collected for {len(baseline_in)} interfaces")

            # Query details for each interface using bulk queries
            for index in interface_indices:
                try:
                    # Use pre-fetched interface name (already filtered)
                    iface_name = all_interfaces.get(index, f"if{index}")

                    # Bulk query all interface properties in a single request
                    # This ensures cache consistency and reduces SNMP round-trips
                    results = await self._get_multiple_oids(
                        [IF_TYPE, IF_SPEED, IF_HIGH_SPEED, IF_OPER_STATUS, IF_ADMIN_STATUS, IF_HC_IN_OCTETS, IF_HC_OUT_OCTETS],
                        str(index)
                    )

                    # Extract values from bulk query results
                    type_id = int(results.get(IF_TYPE) or 0)
                    speed_bps = int(results.get(IF_SPEED) or 0)
                    high_speed_val = results.get(IF_HIGH_SPEED)
                    oper_status = int(results.get(IF_OPER_STATUS) or 2)
                    admin_status = int(results.get(IF_ADMIN_STATUS) or 2)
                    in_octets = results.get(IF_HC_IN_OCTETS)
                    out_octets = results.get(IF_HC_OUT_OCTETS)

                    logger.debug(f"Interface {index} ({iface_name}): ifSpeed raw = {speed_bps}")

                    # Calculate speed in Mbps
                    # If ifSpeed returns 4294967295 (0xFFFFFFFF), use ifHighSpeed instead
                    if speed_bps == 4294967295 or speed_bps >= 4294000000:
                        speed_mbps = int(high_speed_val) if high_speed_val else 0
                        logger.debug(f"Interface {index} ({iface_name}): ifHighSpeed = {speed_mbps} Mbps")
                    else:
                        speed_mbps = speed_bps // 1_000_000
                        logger.debug(f"Interface {index} ({iface_name}): Using ifSpeed, speed_mbps = {speed_mbps}")

                    # Skip interfaces that are down (oper_status != 1)
                    if oper_status != 1:
                        logger.debug(f"Skipping interface {index} ({iface_name}): status is down")
                        continue

                    # Fall back to 32-bit counters if 64-bit not available
                    if in_octets is None:
                        fallback_results = await self._get_multiple_oids([IF_IN_OCTETS, IF_OUT_OCTETS], str(index))
                        in_octets = fallback_results.get(IF_IN_OCTETS)
                        out_octets = fallback_results.get(IF_OUT_OCTETS)

                    # Create interface object
                    interface = NetworkInterface(
                        index=index,
                        name=iface_name,
                        description=iface_name,  # Use same as name (user descriptions not available via SNMP)
                        type_id=type_id,
                        speed=speed_mbps,
                        admin_status=admin_status,
                        oper_status=oper_status,
                        in_octets=in_octets or 0,
                        out_octets=out_octets or 0,
                    )

                    interfaces.append(interface)
                    traffic_info = f", in={in_octets or 0} octets, out={out_octets or 0} octets" if in_octets or out_octets else ""
                    logger.info(
                        f"Interface {index}: {interface.name} ({interface.type_name}, {interface.speed} Mbps, {interface.status}{traffic_info})"
                    )

                except Exception as e:
                    logger.warning(f"Failed to query interface {index}: {e}")
                    continue

            # Wait for traffic to accumulate before taking final measurement
            await asyncio.sleep(2)

            # Second pass: Get final traffic counters to calculate current speed
            final_time = time.time()
            time_delta = final_time - baseline_time
            logger.debug(f"Discovery took {time_delta:.2f}s")

            if time_delta >= 0.5:  # Need at least 0.5 second for meaningful speed calculation
                final_in: Dict[int, int] = {}
                final_out: Dict[int, int] = {}

                # Use bulk queries for each interface to ensure cache consistency
                for iface in interfaces:
                    idx = iface.index
                    results = await self._get_multiple_oids([IF_HC_IN_OCTETS, IF_HC_OUT_OCTETS], str(idx))
                    in_val = results.get(IF_HC_IN_OCTETS)
                    out_val = results.get(IF_HC_OUT_OCTETS)
                    if in_val is not None:
                        final_in[idx] = int(in_val)
                    if out_val is not None:
                        final_out[idx] = int(out_val)

                # Calculate current speeds for all interfaces
                for iface in interfaces:
                    idx = iface.index
                    if idx in baseline_in and idx in final_in:
                        in_delta = final_in[idx] - baseline_in[idx]
                        if in_delta < 0:  # Counter wrap
                            in_delta += 2**64
                        iface.current_in_mbps = (in_delta / time_delta) * 8 / 1_000_000

                    if idx in baseline_out and idx in final_out:
                        out_delta = final_out[idx] - baseline_out[idx]
                        if out_delta < 0:  # Counter wrap
                            out_delta += 2**64
                        iface.current_out_mbps = (out_delta / time_delta) * 8 / 1_000_000

                logger.debug(f"Current speeds calculated for {len(interfaces)} interfaces")
            else:
                logger.warning(f"Discovery too fast ({time_delta:.2f}s) for speed calculation")

            return interfaces

        except Exception as e:
            logger.error(f"Interface discovery error: {e}")
            return []
        finally:
            # Close engine after discovery to free memory
            # It will be recreated on next use
            self._close_engine()
            logger.debug("SNMP engine closed after discovery")

    def suggest_wan_interface(
        self, interfaces: List[NetworkInterface]
    ) -> Optional[NetworkInterface]:
        """
        Suggest the most likely WAN interface based on heuristics.

        Heuristics:
        - Must be operational (status = up)
        - High incoming traffic indicates WAN (download from internet)
        - Look for keywords: WAN, wan, Internet, eth4, igb0, pppoe, wan0
        - Exclude: loopback, local, management, lan, switch, vlan, bridge
        - Prefer ethernet type interfaces
        - UniFi: eth4 is typically WAN1, eth8 is WAN2

        Returns:
            Suggested interface or None
        """
        if not interfaces:
            return None

        # Filter to only operational ethernet interfaces (exclude loopback, tunnel, etc.)
        up_interfaces = [
            iface for iface in interfaces
            if iface.is_up and iface.type_name in ("ethernet", "other")
        ]
        if not up_interfaces:
            logger.warning("No operational ethernet interfaces found")
            return None

        # Find max traffic to normalize scoring
        max_in_traffic = max((iface.in_octets for iface in up_interfaces), default=0)

        # Scoring system
        scored_interfaces = []
        for iface in up_interfaces:
            score = 0
            name_lower = iface.name.lower()
            desc_lower = (iface.description or "").lower()

            # Traffic-based scoring (most important for WAN detection)
            # High incoming traffic suggests this is the WAN interface
            if max_in_traffic > 0 and iface.in_octets > 0:
                traffic_ratio = iface.in_octets / max_in_traffic
                if traffic_ratio > 0.8:  # Top traffic interface
                    score += 50
                elif traffic_ratio > 0.5:
                    score += 30
                elif traffic_ratio > 0.1:
                    score += 10

            # Keyword matching (positive) - WAN indicators
            wan_keywords = ["wan", "internet", "pppoe", "external", "uplink"]
            for keyword in wan_keywords:
                if keyword in name_lower or keyword in desc_lower:
                    score += 25

            # UniFi-specific: eth4 is typically WAN1, eth8 is WAN2
            if name_lower in ("eth4", "eth8"):
                score += 20

            # Physical port naming (eth0-eth9 without VLAN suffix)
            if name_lower.startswith("eth") and "." not in name_lower:
                score += 5

            # pfSense/OPNsense naming
            if name_lower.startswith("igb") or name_lower.startswith("em"):
                score += 5

            # Keyword matching (negative) - LAN/internal indicators
            exclude_keywords = ["loopback", "lo", "local", "management", "lan", "switch", "vlan", "bridge", "br", "dummy"]
            for keyword in exclude_keywords:
                if keyword in name_lower or keyword in desc_lower:
                    score -= 30

            # VLAN interfaces are usually not WAN (indicated by .XX suffix)
            if "." in iface.name:
                score -= 15

            scored_interfaces.append((score, iface))
            logger.debug(
                f"WAN scoring: {iface.name} (idx={iface.index}) -> score={score}, "
                f"in={iface.in_octets / (1024**3):.1f}GB"
            )

        # Sort by score (descending)
        scored_interfaces.sort(key=lambda x: x[0], reverse=True)

        if scored_interfaces and scored_interfaces[0][0] > 0:
            suggested = scored_interfaces[0][1]
            logger.info(
                f"Suggested WAN interface: {suggested.name} (index={suggested.index}, score={scored_interfaces[0][0]}, "
                f"traffic_in={suggested.in_octets / (1024**3):.1f}GB)"
            )
            return suggested
        else:
            # Fall back to interface with highest traffic
            by_traffic = sorted(up_interfaces, key=lambda x: x.in_octets, reverse=True)
            suggested = by_traffic[0]
            logger.info(
                f"No clear WAN match, suggesting highest traffic: {suggested.name} "
                f"(traffic_in={suggested.in_octets / (1024**3):.1f}GB)"
            )
            return suggested

    async def _get_final_readings_with_retry(
        self,
        interface_indices: List[int],
        baseline: Dict[int, Tuple[int, int]],
        baseline_time: float,
        max_retries: int = 2,
    ) -> Dict[int, Tuple[int, int, float]]:
        """
        Get final counter readings with retry logic to handle SNMP cache issues.

        If we detect that the final values equal the baseline (0 delta),
        we retry after a short delay to get fresh data.

        Returns:
            Dict of index -> (in_octets, out_octets, timestamp)
        """
        final_readings = {}

        for attempt in range(max_retries + 1):
            # Close and recreate engine for fresh connection
            self._close_engine()

            # Query interfaces in reverse order with small delays
            reversed_indices = list(reversed(interface_indices))

            for i, idx in enumerate(reversed_indices):
                if idx not in baseline:
                    continue

                # Skip interfaces we already have good readings for
                if idx in final_readings:
                    base_in, base_out = baseline[idx]
                    final_in, final_out, _ = final_readings[idx]
                    if final_in != base_in or final_out != base_out:
                        continue  # Already have a good reading

                if i > 0:
                    await asyncio.sleep(0.3)

                try:
                    results = await self._get_multiple_oids([IF_HC_IN_OCTETS, IF_HC_OUT_OCTETS], str(idx))
                    in_val = results.get(IF_HC_IN_OCTETS)
                    out_val = results.get(IF_HC_OUT_OCTETS)
                    if in_val is not None and out_val is not None:
                        final_readings[idx] = (in_val, out_val, time.time())
                except Exception as e:
                    logger.warning(f"Interface {idx}: final query failed (attempt {attempt + 1}): {e}")

            # Check if we have stale readings (final == baseline)
            stale_count = 0
            for idx in interface_indices:
                if idx in baseline and idx in final_readings:
                    base_in, base_out = baseline[idx]
                    final_in, final_out, _ = final_readings[idx]
                    if final_in == base_in and final_out == base_out:
                        stale_count += 1

            if stale_count == 0 or attempt == max_retries:
                if stale_count > 0 and attempt == max_retries:
                    logger.warning(f"Still have {stale_count} stale readings after {max_retries + 1} attempts")
                break

            # Wait before retry to let cache refresh
            logger.debug(f"Detected {stale_count} stale readings, retrying after delay (attempt {attempt + 1})")
            await asyncio.sleep(2.0)

        return final_readings

    async def poll_interface_speeds(
        self, interface_indices: List[int]
    ) -> Dict[int, Dict[str, any]]:
        """
        Poll current speeds for specific interfaces using self-contained measurement.

        Queries all interfaces together for baseline, waits, then queries all for final.
        Uses a 3-second delay to ensure SNMP cache is refreshed.

        Args:
            interface_indices: List of interface indices to poll

        Returns:
            Dict of index -> {"current_in_mbps": float, "current_out_mbps": float}
        """
        results = {}

        # Get baseline for all interfaces using bulk queries
        baseline_time = time.time()
        baseline = {}
        for idx in interface_indices:
            try:
                results = await self._get_multiple_oids([IF_HC_IN_OCTETS, IF_HC_OUT_OCTETS], str(idx))
                in_val = results.get(IF_HC_IN_OCTETS)
                out_val = results.get(IF_HC_OUT_OCTETS)
                if in_val is not None and out_val is not None:
                    baseline[idx] = (in_val, out_val)
            except Exception as e:
                logger.warning(f"Interface {idx}: baseline failed: {e}")

        if not baseline:
            logger.warning("No baseline data collected")
            return results

        # Wait long enough for SNMP cache to refresh (UniFi devices cache for ~5 seconds)
        # Using 5 seconds ensures we always get fresh data without needing retry logic
        await asyncio.sleep(5.0)

        # Get final readings using bulk queries - with 5s delay, cache should always be fresh
        self._close_engine()
        final_readings = {}

        for idx in interface_indices:
            if idx not in baseline:
                continue
            try:
                results = await self._get_multiple_oids([IF_HC_IN_OCTETS, IF_HC_OUT_OCTETS], str(idx))
                in_val = results.get(IF_HC_IN_OCTETS)
                out_val = results.get(IF_HC_OUT_OCTETS)
                if in_val is not None and out_val is not None:
                    final_readings[idx] = (in_val, out_val, time.time())
            except Exception as e:
                logger.warning(f"Interface {idx}: final query failed: {e}")

        # Process results
        for idx in interface_indices:
            if idx not in baseline or idx not in final_readings:
                continue

            try:
                baseline_in, baseline_out = baseline[idx]
                in_val, out_val, final_time = final_readings[idx]
                time_delta = final_time - baseline_time

                in_delta = in_val - baseline_in
                out_delta = out_val - baseline_out

                # Handle counter wrap
                if in_delta < 0:
                    in_delta += 2**64
                if out_delta < 0:
                    out_delta += 2**64

                current_in_mbps = (in_delta / time_delta) * 8 / 1_000_000
                current_out_mbps = (out_delta / time_delta) * 8 / 1_000_000

                logger.info(
                    f"Interface {idx}: in_delta={in_delta}, out_delta={out_delta}, "
                    f"time_delta={time_delta:.2f}s, speed={current_in_mbps:.2f}/{current_out_mbps:.2f} Mbps"
                )

                results[idx] = {
                    "current_in_mbps": round(current_in_mbps, 2),
                    "current_out_mbps": round(current_out_mbps, 2),
                }

            except Exception as e:
                logger.warning(f"Interface {idx}: calculation failed: {e}")

        return results

    async def get_baseline_counters(self, interface_indices: List[int]) -> Tuple[float, Dict[int, Tuple[int, int]]]:
        """
        Get baseline counters for a list of interfaces.

        Returns:
            Tuple of (timestamp, dict of index -> (in_octets, out_octets))
        """
        baseline_time = time.time()
        baseline_counters = {}

        for idx in interface_indices:
            try:
                results = await self._get_multiple_oids([IF_HC_IN_OCTETS, IF_HC_OUT_OCTETS], str(idx))
                in_val = results.get(IF_HC_IN_OCTETS)
                out_val = results.get(IF_HC_OUT_OCTETS)

                if in_val is not None and out_val is not None:
                    baseline_counters[idx] = (int(in_val), int(out_val))
            except Exception as e:
                logger.debug(f"Failed to get baseline for interface {idx}: {e}")
                continue

        return baseline_time, baseline_counters

    async def close(self):
        """Cleanup SNMP resources."""
        self._close_engine()
        logger.debug("SNMP monitor closed")
