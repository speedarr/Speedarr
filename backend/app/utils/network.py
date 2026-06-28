"""Shared IP / LAN-network classification helpers for media server adapters."""
import ipaddress
from typing import List


def is_private_ip(ip: str) -> bool:
    """True for RFC1918/loopback/link-local/ULA addresses; False on empty/invalid."""
    if not ip:
        return False
    try:
        return ipaddress.ip_address(ip).is_private
    except ValueError:
        return False


def ip_in_networks(ip: str, cidrs: List[str]) -> bool:
    """True if ip falls within any CIDR / bare-IP entry. Malformed inputs are ignored.

    An IPv4 address never matches an IPv6 network and vice versa — only same-version matches are checked.
    """
    if not ip:
        return False
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    for entry in cidrs or []:
        if not isinstance(entry, str) or not entry.strip():
            continue
        try:
            net = ipaddress.ip_network(entry.strip(), strict=False)
        except ValueError:
            continue
        if addr.version == net.version and addr in net:
            return True
    return False


def classify_lan(ip: str, lan_subnets: List[str]) -> bool:
    """LAN if ip is loopback/link-local (safety net) or within one of lan_subnets."""
    if not ip:
        return False
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    if addr.is_loopback or addr.is_link_local:
        return True
    return ip_in_networks(ip, lan_subnets)
