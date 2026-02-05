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
            decisions = [d for d in decisions if _has_limit_changes(d)]
            # Apply offset and limit after filtering
            decisions = decisions[offset:offset + limit]

        decision_list = []
        for d in decisions:
            # Build a human-readable message
            message = _build_decision_message(d)

            decision_list.append({
                "id": d.id,
                "timestamp": d.timestamp.isoformat() if d.timestamp else None,
                "decision_type": d.decision_type,
                "reason": d.reason,
                "message": message,
                "active_streams": d.active_streams,
                "qbittorrent_old_download_limit": d.qbittorrent_old_download_limit,
                "qbittorrent_new_download_limit": d.qbittorrent_new_download_limit,
                "qbittorrent_old_upload_limit": d.qbittorrent_old_upload_limit,
                "qbittorrent_new_upload_limit": d.qbittorrent_new_upload_limit,
                "sabnzbd_old_download_limit": d.sabnzbd_old_download_limit,
                "sabnzbd_new_download_limit": d.sabnzbd_new_download_limit,
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


def _has_limit_changes(d: ThrottleDecision) -> bool:
    """Check if a decision has any actual limit changes."""
    return (
        (d.qbittorrent_old_download_limit is not None and
         d.qbittorrent_new_download_limit is not None and
         d.qbittorrent_old_download_limit != d.qbittorrent_new_download_limit) or
        (d.qbittorrent_old_upload_limit is not None and
         d.qbittorrent_new_upload_limit is not None and
         d.qbittorrent_old_upload_limit != d.qbittorrent_new_upload_limit) or
        (d.sabnzbd_old_download_limit is not None and
         d.sabnzbd_new_download_limit is not None and
         d.sabnzbd_old_download_limit != d.sabnzbd_new_download_limit)
    )


def _build_decision_message(d: ThrottleDecision) -> str:
    """Build a human-readable message for a decision."""
    parts = []

    if d.decision_type == "throttle":
        parts.append("Throttling applied")
    elif d.decision_type == "restore":
        parts.append("Speeds restored")
    elif d.decision_type == "adjust":
        parts.append("Limits adjusted")
    else:
        parts.append(f"Decision: {d.decision_type}")

    # Add qBittorrent changes
    if d.qbittorrent_old_download_limit is not None and d.qbittorrent_new_download_limit is not None:
        if d.qbittorrent_old_download_limit != d.qbittorrent_new_download_limit:
            parts.append(
                f"qBittorrent download: {d.qbittorrent_old_download_limit:.0f} -> {d.qbittorrent_new_download_limit:.0f} Mbps"
            )

    if d.qbittorrent_old_upload_limit is not None and d.qbittorrent_new_upload_limit is not None:
        if d.qbittorrent_old_upload_limit != d.qbittorrent_new_upload_limit:
            parts.append(
                f"qBittorrent upload: {d.qbittorrent_old_upload_limit:.0f} -> {d.qbittorrent_new_upload_limit:.0f} Mbps"
            )

    # Add SABnzbd changes
    if d.sabnzbd_old_download_limit is not None and d.sabnzbd_new_download_limit is not None:
        if d.sabnzbd_old_download_limit != d.sabnzbd_new_download_limit:
            parts.append(
                f"SABnzbd download: {d.sabnzbd_old_download_limit:.0f} -> {d.sabnzbd_new_download_limit:.0f} Mbps"
            )

    # Add stream info
    if d.active_streams is not None and d.active_streams > 0:
        parts.append(f"{d.active_streams} active stream(s)")

    # Add reason if present
    if d.reason:
        parts.append(f"Reason: {d.reason}")

    return " | ".join(parts)
