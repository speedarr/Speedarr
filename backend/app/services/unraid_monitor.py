"""Unraid GraphQL monitor: detect parity check / mover / degraded array.

Mirrors version_service.py: per-request aiohttp session, 10s timeout, never
raises out of get_status() (returns None on any failure so callers can hold
last-known state).
"""
import asyncio
from dataclasses import dataclass
from typing import Optional

import aiohttp
from loguru import logger

from app.config import UnraidConfig

# Disk statuses that mean the array is degraded / a disk is disabled or missing.
DEGRADED_DISK_STATUSES = {"DISK_DSBL", "DISK_INVALID", "DISK_NP_MISSING", "DISK_DSBL_NEW"}

STATUS_QUERY = """
query SpeedarrUnraidStatus {
  array {
    state
    parityCheckStatus { status running progress }
    disks { status type }
    parities { status type }
  }
  vars { shareMoverActive }
}
"""


@dataclass
class UnraidStatus:
    parity_running: bool
    mover_active: bool
    array_degraded: bool
    array_state: str
    parity_progress: Optional[int]


def evaluate_status(data: Optional[dict]) -> UnraidStatus:
    """Pure: map a GraphQL `data` payload to UnraidStatus. Null-safe."""
    # Distinguish between None (healthy default) and {} (degraded default)
    if data is None:
        return UnraidStatus(
            parity_running=False,
            mover_active=False,
            array_degraded=False,
            array_state="UNKNOWN",
            parity_progress=None,
        )

    array = data.get("array") or {}
    vars_ = data.get("vars") or {}
    pc = array.get("parityCheckStatus") or {}

    parity_running = (pc.get("status") == "RUNNING") or bool(pc.get("running"))
    mover_active = bool(vars_.get("shareMoverActive"))
    state = array.get("state") or "UNKNOWN"
    disks = (array.get("disks") or []) + (array.get("parities") or [])
    bad_disk = any((d or {}).get("status") in DEGRADED_DISK_STATUSES for d in disks)
    array_degraded = (state != "STARTED") or bad_disk

    return UnraidStatus(
        parity_running=parity_running,
        mover_active=mover_active,
        array_degraded=array_degraded,
        array_state=state,
        parity_progress=pc.get("progress"),
    )


def compute_unraid_reasons(status: UnraidStatus, cfg: UnraidConfig) -> list[str]:
    """Active throttle reasons given the status and which conditions are enabled."""
    reasons = []
    if cfg.throttle_on_parity_check and status.parity_running:
        reasons.append("parity_check")
    if cfg.throttle_on_mover and status.mover_active:
        reasons.append("mover")
    if cfg.throttle_on_array_degraded and status.array_degraded:
        reasons.append("array_degraded")
    return reasons


class UnraidMonitor:
    def __init__(self, config: UnraidConfig):
        self.config = config

    def _endpoint(self) -> str:
        base = (self.config.url or "").rstrip("/")
        return base if base.endswith("/graphql") else f"{base}/graphql"

    async def _post(self) -> Optional[dict]:
        """POST the status query. Returns the GraphQL `data` dict, or None on any error."""
        if not self.config.url or not self.config.api_key:
            logger.warning("Unraid monitor missing url or api_key")
            return None
        ssl_param = None if self.config.verify_ssl else False
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                headers = {"x-api-key": self.config.api_key, "Content-Type": "application/json"}
                async with session.post(
                    self._endpoint(), json={"query": STATUS_QUERY}, headers=headers, ssl=ssl_param
                ) as resp:
                    if resp.status != 200:
                        logger.warning(f"Unraid API returned status {resp.status}")
                        return None
                    body = await resp.json()
            if body.get("errors"):
                logger.warning(f"Unraid GraphQL errors: {body['errors']}")
                return None
            return body.get("data")
        except asyncio.TimeoutError:
            logger.warning("Timeout polling Unraid API")
            return None
        except Exception as e:
            logger.warning(f"Error polling Unraid API: {e}")
            return None

    async def get_status(self) -> Optional[UnraidStatus]:
        data = await self._post()
        return evaluate_status(data) if data is not None else None

    async def test_connection(self) -> tuple[bool, str]:
        status = await self.get_status()
        if status is None:
            return False, "Failed to reach Unraid GraphQL API. Check URL, API key, and that the Connect/API plugin is enabled."
        return True, (
            f"Connected. Array {status.array_state}, "
            f"parity {'running' if status.parity_running else 'idle'}, "
            f"mover {'active' if status.mover_active else 'idle'}."
        )
