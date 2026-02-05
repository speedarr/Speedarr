"""
Bandwidth calculation utilities.
"""
from typing import Dict, Any, List


def mbps_to_bytes_per_sec(mbps: float) -> int:
    """Convert Megabits per second to bytes per second."""
    return int(mbps * 1_000_000 / 8)


def bytes_per_sec_to_mbps(bytes_per_sec: int) -> float:
    """Convert bytes per second to Megabits per second."""
    return (bytes_per_sec * 8) / 1_000_000


def mbps_to_kbps(mbps: float) -> float:
    """Convert Megabits per second to Kilobits per second."""
    return mbps * 1_000


def kbps_to_mbps(kbps: float) -> float:
    """Convert Kilobits per second to Megabits per second."""
    return kbps / 1_000


def format_speed(mbps: float) -> str:
    """Format speed for human-readable display."""
    if mbps >= 1000:
        return f"{mbps / 1000:.1f} Gbps"
    return f"{mbps:.1f} Mbps"


def calculate_stream_bandwidth(stream: Dict[str, Any], overhead_percent: float = 20) -> float:
    """
    Calculate required bandwidth for a stream.

    Args:
        stream: Stream data dict
        overhead_percent: Protocol overhead percentage to add (clamped to 0-300)

    Returns:
        Required bandwidth in Mbps (always >= 0)
    """
    # Clamp overhead to reasonable range (0-300%)
    overhead_percent = max(0, min(300, overhead_percent))

    # Get bitrate from stream - treat 0 or negative as missing
    bitrate = stream.get("stream_bitrate_mbps", 0)
    if bitrate and bitrate > 0:
        base_bandwidth = bitrate
    else:
        # Fallback: estimate based on quality
        quality = (stream.get("quality_profile") or "").lower()
        if "4k" in quality or "2160" in quality:
            base_bandwidth = 40.0
        elif "1080" in quality or "hd" in quality:
            base_bandwidth = 12.0
        elif "720" in quality:
            base_bandwidth = 6.0
        else:
            base_bandwidth = 4.0  # SD fallback

    # Add overhead for transcoding, protocol, etc.
    overhead_multiplier = 1 + (overhead_percent / 100)
    result = base_bandwidth * overhead_multiplier

    # Ensure non-negative result
    return max(0, result)


def filter_streams_for_bandwidth(
    streams: List[Dict[str, Any]],
    include_lan_streams: bool = False
) -> List[Dict[str, Any]]:
    """
    Filter streams for bandwidth calculations based on LAN/WAN config.

    Args:
        streams: List of stream data dicts
        include_lan_streams: If False, excludes LAN streams from calculations

    Returns:
        Filtered list of streams to use for bandwidth calculations
    """
    if include_lan_streams:
        return streams
    return [s for s in streams if not s.get("is_lan", False)]


def calculate_total_stream_bitrate(streams: List[Dict[str, Any]]) -> float:
    """
    Calculate total bitrate for a list of streams.

    Args:
        streams: List of stream data dicts

    Returns:
        Total bitrate in Mbps
    """
    return sum(s.get("stream_bitrate_mbps", 0) for s in streams)
