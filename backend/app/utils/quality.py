"""
Normalize per-server resolution tokens into one canonical vocabulary.

Plex hands back a clean token via Media.videoResolution ("4k", "1080", "sd").
Jellyfin/Emby only expose the resolution inside the video stream's DisplayTitle
(e.g. "1080p H264 SDR"), which also leaks any embedded stream Title — so we
extract just the resolution token from it. No width/height math: the resolution
is always already present as a token, we only need to recognize and canonicalize it.
"""
import re
from typing import Optional

# Matches a resolution-shaped token: 3-4 digits followed by 'p', or 4K/8K.
# Codec/range fragments (H264, HEVC, SDR, AAC) carry no such token and are ignored.
_RES_TOKEN = re.compile(r"(\d{3,4}p|[48]K)", re.IGNORECASE)

_CANON = {
    "8k": "8K", "4k": "4K", "2160p": "4K",
    "1080p": "1080p", "1080": "1080p",
    "720p": "720p", "720": "720p",
    "480p": "480p", "480": "480p",
    "360p": "SD", "240p": "SD", "sd": "SD",
}


def canonical_resolution(token: Optional[str]) -> Optional[str]:
    """Map a raw resolution token to the canonical label, or None if unrecognized."""
    if not token:
        return None
    return _CANON.get(token.strip().lower())


def resolution_from_display_title(display_title: Optional[str]) -> Optional[str]:
    """Extract the canonical resolution from a Jellyfin/Emby video DisplayTitle.

    Takes the LAST resolution token: Jellyfin appends the auto-generated
    "<res> <codec> <range>" after any leaked stream Title, so the last token is
    the real resolution even when a title leaks. Returns None when none is found
    (e.g. an audio stream's DisplayTitle).
    """
    if not display_title:
        return None
    matches = _RES_TOKEN.findall(display_title)
    return canonical_resolution(matches[-1]) if matches else None
