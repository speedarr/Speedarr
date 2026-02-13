"""
Speedarr - Intelligent bandwidth management for Plex and download clients.
"""

import os

__version__ = os.getenv("SPEEDARR_VERSION", "dev")
__commit__ = os.getenv("SPEEDARR_COMMIT", "unknown")
__branch__ = os.getenv("SPEEDARR_BRANCH", "unknown")
