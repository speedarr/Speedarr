"""
Formatting utilities for display values.
"""


def format_display_title(stream: dict) -> str:
    """Format display title based on media type.

    For TV episodes: "Show Name - S01E01"
    For movies: "Movie Title"
    """
    media_type = (stream.get("media_type") or "").lower()

    if media_type == "episode":
        show = stream.get("grandparent_title") or ""
        season = stream.get("season_number")
        episode = stream.get("episode_number")

        if show and season is not None and episode is not None:
            return f"{show} - S{season:02d}E{episode:02d}"
        elif show:
            return show

    return stream.get("media_title") or "Unknown"
