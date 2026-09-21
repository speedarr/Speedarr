"""Unit helpers convert between decimal Mbps and each client's native byte unit.

Speedarr's internal unit is decimal megabits per second (1 Mbps = 125,000 bytes/s),
matching Plex bitrates and ISP-quoted line speeds. Clients variously want bytes/s,
kilobytes/s (1000) or kibibytes/s (1024); these helpers are the single place that
knows the difference.
"""
import pytest

from app.utils.bandwidth import (
    bytes_per_sec_to_mbps,
    kibibytes_per_sec_to_mbps,
    kilobytes_per_sec_to_mbps,
    mbps_to_bytes_per_sec,
    mbps_to_kibibytes_per_sec,
    mbps_to_kilobytes_per_sec,
)


def test_ten_mbps_is_1_250_000_bytes_per_sec():
    assert mbps_to_bytes_per_sec(10.0) == 1_250_000
    assert bytes_per_sec_to_mbps(1_250_000) == pytest.approx(10.0)


def test_kilobytes_use_1000_bytes():
    assert mbps_to_kilobytes_per_sec(8.0) == pytest.approx(1000.0)
    assert kilobytes_per_sec_to_mbps(1000.0) == pytest.approx(8.0)


def test_kibibytes_use_1024_bytes():
    # 8.192 Mbps = 1,024,000 bytes/s = exactly 1000 KiB/s
    assert mbps_to_kibibytes_per_sec(8.192) == pytest.approx(1000.0)
    assert kibibytes_per_sec_to_mbps(1000.0) == pytest.approx(8.192)


def test_kibibyte_and_kilobyte_helpers_differ_by_the_binary_ratio():
    kib = mbps_to_kibibytes_per_sec(10.0)
    kb = mbps_to_kilobytes_per_sec(10.0)
    assert kb / kib == pytest.approx(1.024)


@pytest.mark.parametrize("mbps", [0.01, 1.0, 37.5, 940.0])
def test_round_trips_are_lossless(mbps):
    assert kibibytes_per_sec_to_mbps(mbps_to_kibibytes_per_sec(mbps)) == pytest.approx(mbps)
    assert kilobytes_per_sec_to_mbps(mbps_to_kilobytes_per_sec(mbps)) == pytest.approx(mbps)
