"""SNMP rate calculation — sliding-window averaging defeats counter-cache aliasing.

Background (the bug this guards against): many WAN gateways quantize their SNMP
ifHCInOctets/ifHCOutOctets counters to a fixed internal refresh (commonly ~5s).
When Speedarr polls at a near-identical interval, differencing only the two most
recent reads aliases: each poll window randomly contains 0, 1, or 2 device
refresh steps, producing a 0 / 1x / 2x sawtooth (idle: 0<->30 Mbps; busy:
950 -> 1900 Mbps spikes). Averaging the cumulative-counter delta over a window
several times the device refresh interval cancels the aliasing.
"""
from app.services.snmp_monitor import compute_windowed_rate


# 10 Mbps true rate => 1.25 MB/s of octets.
TRUE_MBPS = 10.0
R = int(TRUE_MBPS * 1_000_000 / 8)  # bytes/sec


def _aliased_samples():
    """A device with a 5s counter refresh, polled at staggered times so reads
    land both on stale (no refresh) and post-refresh boundaries.

    counter(t) = R * 5 * floor(t / 5)  (counter only advances at 5s refresh ticks)
    """
    times = [0, 3, 5, 8, 10, 13, 15, 18, 20]
    return [(float(t), R * 5 * (t // 5), R * 5 * (t // 5)) for t in times]


def test_input_actually_aliases_with_naive_two_point_differencing():
    """Sanity-check the fixture: adjacent-read differencing DOES spike, so the
    windowed test below is proving something real."""
    samples = _aliased_samples()
    naive_rates = []
    for (t0, in0, _), (t1, in1, _) in zip(samples, samples[1:]):
        naive_rates.append((in1 - in0) / (t1 - t0) * 8 / 1_000_000)
    # Naive differencing yields the pathological 0 / ~2.5x sawtooth.
    assert min(naive_rates) == 0.0
    assert max(naive_rates) > 2 * TRUE_MBPS


def test_windowed_rate_cancels_aliasing():
    """Oldest-vs-newest over the full window recovers the true average rate."""
    down, up = compute_windowed_rate(_aliased_samples(), use_64bit=True)
    assert abs(down - TRUE_MBPS) < 0.5
    assert abs(up - TRUE_MBPS) < 0.5


def test_returns_none_for_insufficient_samples():
    assert compute_windowed_rate([], use_64bit=True) is None
    assert compute_windowed_rate([(1.0, 100, 100)], use_64bit=True) is None
    # Too short a span can't give a meaningful rate.
    assert compute_windowed_rate([(1.0, 100, 100), (1.2, 200, 200)], use_64bit=True) is None


def test_counter_wrap_is_handled():
    """A 64-bit counter that wraps past 2**64 yields a positive delta, not a
    massive negative one."""
    max64 = 2 ** 64
    samples = [(0.0, max64 - 1_000_000, 0), (10.0, 250_000, 0)]
    down, up = compute_windowed_rate(samples, use_64bit=True)
    # delta = (250_000 + 1_000_000) bytes over 10s
    expected = (1_250_000 / 10.0) * 8 / 1_000_000
    assert abs(down - expected) < 0.01


def test_64bit_flag_selects_wrap_modulus():
    """A 32-bit counter wrap must use the 2**32 modulus, not 2**64."""
    max32 = 2 ** 32
    samples = [(0.0, max32 - 500_000, 0), (10.0, 500_000, 0)]
    down, _ = compute_windowed_rate(samples, use_64bit=False)
    expected = (1_000_000 / 10.0) * 8 / 1_000_000
    assert abs(down - expected) < 0.01
