"""
GitHub release version checker with in-memory cache.
"""

import asyncio
import time
from typing import Optional

import aiohttp
from loguru import logger

GITHUB_API_URL = "https://api.github.com/repos/speedarr/Speedarr/releases/latest"
GITHUB_COMMITS_URL = "https://api.github.com/repos/speedarr/Speedarr/commits/develop"
CACHE_TTL_SECONDS = 3600  # 1 hour


def _parse_version(version_str: str) -> Optional[tuple]:
    """Parse a version string like 'v1.2.3' or '1.2.3' into a tuple of ints."""
    cleaned = version_str.lstrip("v").strip()
    try:
        return tuple(int(part) for part in cleaned.split("."))
    except (ValueError, AttributeError):
        return None


class VersionChecker:
    def __init__(self):
        self._cache: Optional[dict] = None
        self._cache_time: float = 0
        self._develop_cache: Optional[dict] = None
        self._develop_cache_time: float = 0
        self._lock = asyncio.Lock()

    async def check_for_updates(
        self,
        current_version: str,
        current_commit: str = "",
        current_branch: str = "",
        force_refresh: bool = False,
    ) -> dict:
        """Check GitHub for the latest release or develop commit.

        Returns a dict with update_available, latest_version/latest_commit,
        release_url, and optional error.
        """
        # Dev/develop versions check against latest develop commit
        if current_version in ("dev", "develop") or current_version.startswith("dev"):
            # Local builds can't be compared
            if not current_commit or current_commit in ("local", "unknown"):
                return {"update_available": False}

            # Check develop cache
            if (
                not force_refresh
                and self._develop_cache
                and (time.time() - self._develop_cache_time) < CACHE_TTL_SECONDS
            ):
                return self._develop_cache

            async with self._lock:
                if (
                    not force_refresh
                    and self._develop_cache
                    and (time.time() - self._develop_cache_time) < CACHE_TTL_SECONDS
                ):
                    return self._develop_cache

                result = await self._check_develop_updates(current_commit)
                self._develop_cache = result
                self._develop_cache_time = time.time()
                return result

        # Return cached result if still valid
        if not force_refresh and self._cache and (time.time() - self._cache_time) < CACHE_TTL_SECONDS:
            return self._cache

        async with self._lock:
            # Double-check cache after acquiring lock
            if not force_refresh and self._cache and (time.time() - self._cache_time) < CACHE_TTL_SECONDS:
                return self._cache

            result = await self._fetch_latest_release(current_version)
            self._cache = result
            self._cache_time = time.time()
            return result

    async def _check_develop_updates(self, current_commit: str) -> dict:
        """Check if a newer develop commit exists on GitHub."""
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                headers = {"Accept": "application/vnd.github.v3+json"}
                async with session.get(GITHUB_COMMITS_URL, headers=headers) as resp:
                    if resp.status == 403:
                        logger.warning("GitHub API rate limit reached during develop version check")
                        return {"update_available": False, "error": "Rate limit reached"}

                    if resp.status != 200:
                        logger.warning(f"GitHub API returned status {resp.status} during develop version check")
                        return {"update_available": False, "error": f"GitHub API error ({resp.status})"}

                    data = await resp.json()

            latest_sha = data.get("sha", "")
            if not latest_sha:
                return {"update_available": False, "error": "Could not parse commit"}

            # Compare: current_commit is a short SHA (7 chars), latest_sha is full 40-char
            update_available = not latest_sha.startswith(current_commit)
            latest_short = latest_sha[:7]

            result = {"update_available": update_available}
            if update_available:
                result["latest_commit"] = latest_short
                result["release_url"] = f"https://github.com/speedarr/Speedarr/compare/{current_commit}...develop"

            return result

        except asyncio.TimeoutError:
            logger.warning("Timeout checking for develop updates from GitHub")
            return {"update_available": False, "error": "Request timed out"}
        except Exception as e:
            logger.warning(f"Error checking for develop updates: {e}")
            return {"update_available": False, "error": "Could not check for updates"}

    async def _fetch_latest_release(self, current_version: str) -> dict:
        """Fetch the latest release from GitHub API."""
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                headers = {"Accept": "application/vnd.github.v3+json"}
                async with session.get(GITHUB_API_URL, headers=headers) as resp:
                    if resp.status == 403:
                        logger.warning("GitHub API rate limit reached during version check")
                        return {"update_available": False, "error": "Rate limit reached"}

                    if resp.status != 200:
                        logger.warning(f"GitHub API returned status {resp.status} during version check")
                        return {"update_available": False, "error": f"GitHub API error ({resp.status})"}

                    data = await resp.json()

            tag_name = data.get("tag_name", "")
            release_url = data.get("html_url", "")

            current_parsed = _parse_version(current_version)
            latest_parsed = _parse_version(tag_name)

            if not current_parsed or not latest_parsed:
                return {
                    "update_available": False,
                    "latest_version": tag_name.lstrip("v"),
                    "release_url": release_url,
                    "error": "Could not parse version",
                }

            update_available = latest_parsed > current_parsed

            return {
                "update_available": update_available,
                "latest_version": tag_name.lstrip("v"),
                "release_url": release_url,
            }

        except asyncio.TimeoutError:
            logger.warning("Timeout checking for updates from GitHub")
            return {"update_available": False, "error": "Request timed out"}
        except Exception as e:
            logger.warning(f"Error checking for updates: {e}")
            return {"update_available": False, "error": "Could not check for updates"}


# Module-level singleton
version_checker = VersionChecker()
