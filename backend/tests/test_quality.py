"""Pure resolution-token normalization shared by all media-server adapters."""
import pytest
from app.utils.quality import canonical_resolution, resolution_from_display_title


@pytest.mark.parametrize("raw,expected", [
    ("4k", "4K"),          # Plex lowercase token
    ("4K", "4K"),
    ("2160p", "4K"),       # Jellyfin may emit 2160p for UHD
    ("8k", "8K"),
    ("1080", "1080p"),     # Plex numeric token (no 'p')
    ("1080p", "1080p"),
    ("720", "720p"),
    ("720p", "720p"),
    ("480", "480p"),
    ("480p", "480p"),
    ("sd", "SD"),
    ("360p", "SD"),
    ("240p", "SD"),
    ("  1080P  ", "1080p"),  # whitespace + case insensitive
    ("1440p", None),         # recognized-but-unmapped -> no badge
    ("garbage", None),
    ("", None),
    (None, None),
])
def test_canonical_resolution(raw, expected):
    assert canonical_resolution(raw) == expected


@pytest.mark.parametrize("display_title,expected", [
    ("1080p H264 SDR", "1080p"),
    ("All Good Things - 1080p - H264 - SDR", "1080p"),  # the title-leak case
    ("720p Movie - 1080p H264", "1080p"),               # last-match: real trailing res beats a leaked-title token
    ("4K HEVC HDR", "4K"),
    ("2160p HEVC Dolby Vision", "4K"),
    ("720p H264", "720p"),
    ("English - AAC - Stereo - Default", None),          # audio stream, no resolution
    ("Director's Commentary", None),                     # no resolution token at all
    ("", None),
    (None, None),
])
def test_resolution_from_display_title(display_title, expected):
    assert resolution_from_display_title(display_title) == expected
