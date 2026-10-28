"""
Factory for the WAN bandwidth monitor selected in the ``snmp`` settings section.

Both monitors expose ``get_bandwidth()``, ``test_connection()`` and ``close()``
and return ``{"download": Mbps, "upload": Mbps}``, so callers don't need to know
which source is configured.
"""
from app.config import SNMPConfig


def create_wan_monitor(config: SNMPConfig):
    """Return an SNMPMonitor or FritzBoxMonitor for ``config.source``."""
    if config.source == "fritzbox":
        from app.services.fritzbox_monitor import FritzBoxMonitor
        return FritzBoxMonitor(config)

    from app.services.snmp_monitor import SNMPMonitor
    return SNMPMonitor(config)


def describe_wan_monitor(config: SNMPConfig) -> str:
    """Short human-readable description for log lines."""
    if config.source == "fritzbox":
        return f"FRITZ!Box at {config.host}"
    return f"SNMP interface {config.interface}"
