"""
Decision logs API routes.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta, timezone
from loguru import logger

from app.models import ThrottleDecision
from app.database import get_db

router = APIRouter(prefix="/api/decisions", tags=["decisions"])


@router.get("/logs")
async def get_decision_logs(
    days: int = Query(7, ge=1, le=90, description="Number of days to retrieve"),
    limit: int = Query(100, ge=1, le=500, description="Maximum number of records"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    changes_only: bool = Query(False, description="Only return logs where limits actually changed"),
    db: AsyncSession = Depends(get_db),
):
    """
    Get throttle decision logs.

    Returns historical decisions about bandwidth throttling.
    """
    try:
        # Build base query
        query = select(ThrottleDecision).where(
            ThrottleDecision.timestamp >= datetime.now(timezone.utc) - timedelta(days=days)
        ).order_by(desc(ThrottleDecision.timestamp))

        # If changes_only, we need to filter after fetching since the logic is complex
        # Fetch more records to ensure we can get enough after filtering
        if changes_only:
            query = query.limit(limit * 10)  # Fetch more to filter from
        else:
            query = query.limit(limit).offset(offset)

        result = await db.execute(query)
        decisions = result.scalars().all()

        # Filter to only changes if requested
        if changes_only:
            decisions = [d for d in decisions if has_limit_changes(decision_client_map(d))]
            # Apply offset and limit after filtering
            decisions = decisions[offset:offset + limit]

        decision_list = []
        for d in decisions:
            client_map = decision_client_map(d)
            decision_list.append({
                "id": d.id,
                "timestamp": d.timestamp.isoformat() if d.timestamp else None,
                "decision_type": d.decision_type,
                "reason": d.reason,
                "message": build_decision_message(d.decision_type, client_map, d.active_streams, d.reason),
                "active_streams": d.active_streams,
                "per_client": client_map,
                "triggered_by": d.triggered_by,
            })

        return {
            "logs": decision_list,
            "total": len(decision_list),
            "days": days,
            "limit": limit,
            "offset": offset
        }

    except Exception as e:
        logger.error(f"Error getting decision logs: {e}")
        return {"logs": [], "total": 0, "error": str(e)}


_LIMIT_DIRECTIONS = (
    ("old_download_limit", "new_download_limit", "download"),
    ("old_upload_limit", "new_upload_limit", "upload"),
)


def decision_client_map(d) -> dict:
    """Per-client map for a decision row.

    Prefers the per_client JSON; for pre-migration rows it synthesizes the map
    from the legacy qbittorrent_*/sabnzbd_* columns so old history still renders.
    """
    if getattr(d, "per_client", None):
        return d.per_client
    legacy = {}
    qb = {}
    if d.qbittorrent_old_download_limit is not None or d.qbittorrent_new_download_limit is not None:
        qb["old_download_limit"] = d.qbittorrent_old_download_limit
        qb["new_download_limit"] = d.qbittorrent_new_download_limit
    if d.qbittorrent_old_upload_limit is not None or d.qbittorrent_new_upload_limit is not None:
        qb["old_upload_limit"] = d.qbittorrent_old_upload_limit
        qb["new_upload_limit"] = d.qbittorrent_new_upload_limit
    if qb:
        legacy["qbittorrent"] = {"name": "qBittorrent", "type": "qbittorrent", **qb}
    sab = {}
    if d.sabnzbd_old_download_limit is not None or d.sabnzbd_new_download_limit is not None:
        sab["old_download_limit"] = d.sabnzbd_old_download_limit
        sab["new_download_limit"] = d.sabnzbd_new_download_limit
    if sab:
        legacy["sabnzbd"] = {"name": "SABnzbd", "type": "sabnzbd", **sab}
    return legacy


def has_limit_changes(client_map: dict) -> bool:
    """True if any client entry has a real old!=new limit change."""
    for entry in client_map.values():
        for old_k, new_k, _ in _LIMIT_DIRECTIONS:
            o, n = entry.get(old_k), entry.get(new_k)
            if o is not None and n is not None and o != n:
                return True
    return False


def build_decision_message(decision_type, client_map: dict, active_streams, reason) -> str:
    """Human-readable per-client decision message."""
    parts = []
    if decision_type == "throttle":
        parts.append("Throttling applied")
    elif decision_type == "restore":
        parts.append("Speeds restored")
    elif decision_type == "adjust":
        parts.append("Limits adjusted")
    else:
        parts.append(f"Decision: {decision_type}")

    for entry in client_map.values():
        name = entry.get("name", "Client")
        for old_k, new_k, label in _LIMIT_DIRECTIONS:
            o, n = entry.get(old_k), entry.get(new_k)
            if o is not None and n is not None and o != n:
                parts.append(f"{name} {label}: {o:.0f} -> {n:.0f} Mbps")

    if active_streams:
        parts.append(f"{active_streams} active stream(s)")
    if reason:
        parts.append(f"Reason: {reason}")
    return " | ".join(parts)
