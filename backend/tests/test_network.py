"""Pure IP / LAN-network classification helpers."""
from app.utils.network import is_private_ip, ip_in_networks, classify_lan


def test_is_private_ip_true_for_rfc1918():
    assert is_private_ip("192.168.1.20") is True
    assert is_private_ip("10.0.60.168") is True
    assert is_private_ip("172.16.5.5") is True


def test_is_private_ip_false_for_public_and_invalid():
    assert is_private_ip("8.8.8.8") is False
    assert is_private_ip("") is False
    assert is_private_ip("not-an-ip") is False


def test_ip_in_networks_ipv4_membership():
    assert ip_in_networks("192.168.5.42", ["192.168.5.0/24"]) is True
    # The exact bug case: client outside the server's LAN subnet -> not a member
    assert ip_in_networks("192.168.10.158", ["192.168.5.0/24"]) is False


def test_ip_in_networks_handles_bare_ip_and_multiple_entries():
    assert ip_in_networks("10.0.0.5", ["192.168.5.0/24", "10.0.0.0/8"]) is True
    assert ip_in_networks("10.0.0.5", ["10.0.0.5"]) is True


def test_ip_in_networks_ipv6():
    assert ip_in_networks("fd00::5", ["fd00::/8"]) is True
    assert ip_in_networks("2001:4860::1", ["fd00::/8"]) is False


def test_ip_in_networks_ignores_malformed_entries_and_inputs():
    assert ip_in_networks("192.168.5.42", ["garbage", "192.168.5.0/24"]) is True
    assert ip_in_networks("192.168.5.42", ["", None]) is False  # type: ignore[list-item]
    assert ip_in_networks("nope", ["192.168.5.0/24"]) is False
    assert ip_in_networks("", ["192.168.5.0/24"]) is False


def test_classify_lan_loopback_and_link_local_always_lan():
    assert classify_lan("127.0.0.1", []) is True
    assert classify_lan("fe80::1", []) is True


def test_classify_lan_membership_else_false():
    assert classify_lan("192.168.5.42", ["192.168.5.0/24"]) is True
    assert classify_lan("192.168.10.158", ["192.168.5.0/24"]) is False
    assert classify_lan("8.8.8.8", ["192.168.5.0/24"]) is False
    assert classify_lan("bad-ip", ["192.168.5.0/24"]) is False
