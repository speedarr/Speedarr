"""
Streams API routes for viewing active and historical stream data.
"""
from fastapi import APIRouter, Depends, Request, HTTPException, Query
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from datetime import datetime, timedelta, timezone
from loguru import logger

from app.models import StreamHistory, BandwidthMetric
from app.database import get_db
from app.utils.formatting import format_display_title
from app.utils.errors import log_and_raise_500
from sqlalchemy import func

router = APIRouter(prefix="/api/streams", tags=["streams"])


@router.get("/active")
async def get_active_streams(
    request: Request,

):
    """
    Get currently active Plex streams from the polling monitor.

    Returns real-time stream data including bandwidth usage.
    """
    try:
        polling_monitor = request.app.state.polling_monitor

        # Get cached streams from polling monitor
        active_streams = polling_monitor._cached_streams or []

        # Add display_title to each stream
        streams_with_display = [
            {**s, "display_title": format_display_title(s)}
            for s in active_streams
        ]

        # Get reserved bandwidth info
        reservations = polling_monitor._reservations or []

        return {
            "active_streams": streams_with_display,
            "total_streams": len(active_streams),
            "total_bandwidth_mbps": sum(s.get("stream_bitrate_mbps", 0) for s in active_streams),
            "reservations": [
                {
                    "id": r.get("id"),
                    "user_id": r.get("user_id"),
                    "user_name": r.get("user_name"),
                    "media_title": r.get("media_title"),
                    "player": r.get("player"),
                    "bandwidth_mbps": r.get("bandwidth_mbps"),
                    "expires_at": r.get("expires_at").isoformat().replace('+00:00', 'Z') if r.get("expires_at") else None,
                    "remaining_seconds": (r.get("expires_at") - datetime.now(timezone.utc)).total_seconds() if r.get("expires_at") else 0
                }
                for r in reservations
            ],
            "total_reserved_mbps": sum(r.get("bandwidth_mbps", 0) for r in reservations)
        }

    except Exception as e:
        log_and_raise_500(e, "get active streams")


@router.get("/history")
async def get_stream_history(
    days: int = Query(7, ge=1, le=90, description="Number of days to retrieve"),
    user_id: Optional[str] = Query(None, description="Filter by user ID"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of records"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    db: AsyncSession = Depends(get_db),

):
    """
    Get historical stream data from the database.

    Supports filtering by user and date range with pagination.
    """
    try:
        # Build query
        query = select(StreamHistory).where(
            StreamHistory.started_at >= datetime.now(timezone.utc) - timedelta(days=days)
        )

        if user_id:
            query = query.where(StreamHistory.user_id == user_id)

        # Order by most recent first
        query = query.order_by(desc(StreamHistory.started_at))

        # Apply pagination
        query = query.limit(limit).offset(offset)

        # Execute query
        result = await db.execute(query)
        streams = result.scalars().all()

        # Convert to dict and add display_title
        stream_list = []
        for s in streams:
            stream_dict = {
                "id": s.id,
                "session_id": s.session_id,
                "user_name": s.user_name,
                "user_id": s.user_id,
                "media_title": s.media_title,
                "media_type": s.media_type,
                "grandparent_title": s.grandparent_title,
                "parent_title": s.parent_title,
                "started_at": s.started_at.isoformat() if s.started_at else None,
                "ended_at": s.ended_at.isoformat() if s.ended_at else None,
                "duration_seconds": s.duration_seconds,
                "stream_bandwidth_mbps": s.stream_bandwidth_mbps,
                "quality_profile": s.quality_profile,
                "player": s.player,
                "ip_address": s.ip_address
            }
            stream_dict["display_title"] = format_display_title(stream_dict)
            stream_list.append(stream_dict)

        return {
            "streams": stream_list,
            "total": len(stream_list),
            "days": days,
            "limit": limit,
            "offset": offset
        }

    except Exception as e:
        log_and_raise_500(e, "get stream history")


@router.get("/history/{stream_id}")
async def get_stream_details(
    stream_id: int,
    db: AsyncSession = Depends(get_db),

):
    """
    Get detailed information about a specific stream session.
    """
    try:
        result = await db.execute(
            select(StreamHistory).where(StreamHistory.id == stream_id)
        )
        stream = result.scalar_one_or_none()

        if not stream:
            raise HTTPException(status_code=404, detail="Stream not found")

        return {
            "id": stream.id,
            "session_id": stream.session_id,
            "user_name": stream.user_name,
            "user_id": stream.user_id,
            "media_title": stream.media_title,
            "media_type": stream.media_type,
            "started_at": stream.started_at.isoformat() if stream.started_at else None,
            "ended_at": stream.ended_at.isoformat() if stream.ended_at else None,
            "duration_seconds": stream.duration_seconds,
            "stream_bandwidth_mbps": stream.stream_bandwidth_mbps,
            "quality_profile": stream.quality_profile,
            "transcode_decision": stream.transcode_decision,
            "player": stream.player,
            "platform": stream.platform,
            "ip_address": stream.ip_address,
            "created_date": stream.created_date.isoformat() if stream.created_date else None
        }

    except HTTPException:
        raise
    except Exception as e:
        log_and_raise_500(e, "get stream details")


@router.get("/summary")
async def get_stream_summary(
    days: int = Query(7, ge=1, le=90, description="Number of days for summary"),
    db: AsyncSession = Depends(get_db),

):
    """
    Get summary statistics for streams over a time period.
    """
    try:
        # Get all streams in the time period
        result = await db.execute(
            select(StreamHistory).where(
                StreamHistory.started_at >= datetime.now(timezone.utc) - timedelta(days=days)
            )
        )
        streams = result.scalars().all()

        # Get peak combined bandwidth from BandwidthMetric table
        peak_combined_result = await db.execute(
            select(func.max(BandwidthMetric.total_stream_bandwidth)).where(
                BandwidthMetric.timestamp >= datetime.now(timezone.utc) - timedelta(days=days)
            )
        )
        peak_combined_bandwidth = peak_combined_result.scalar() or 0

        if not streams:
            return {
                "total_streams": 0,
                "unique_users": 0,
                "total_bandwidth_gb": 0,
                "avg_bandwidth_mbps": 0,
                "min_bandwidth_mbps": 0,
                "peak_individual_bandwidth_mbps": 0,
                "peak_combined_bandwidth_mbps": round(peak_combined_bandwidth, 2),
                "avg_stream_duration_minutes": 0,
                "total_duration_hours": 0,
                "days": days,
                "most_common_quality": "Unknown"
            }

        # Calculate statistics
        unique_users = len(set(s.user_name for s in streams if s.user_name))
        total_duration_seconds = sum(s.duration_seconds or 0 for s in streams)

        # Filter out 0 and null bandwidth values for min/avg calculations
        bandwidths_nonzero = [s.stream_bandwidth_mbps for s in streams
                              if s.stream_bandwidth_mbps is not None and s.stream_bandwidth_mbps > 0]
        all_bandwidths = [s.stream_bandwidth_mbps for s in streams if s.stream_bandwidth_mbps is not None]

        avg_bandwidth = sum(bandwidths_nonzero) / len(bandwidths_nonzero) if bandwidths_nonzero else 0
        min_bandwidth = min(bandwidths_nonzero) if bandwidths_nonzero else 0
        peak_individual_bandwidth = max(all_bandwidths) if all_bandwidths else 0

        # Estimate total bandwidth usage (bandwidth * duration)
        total_bandwidth_mb = sum(
            (s.stream_bandwidth_mbps or 0) * (s.duration_seconds or 0) / 60
            for s in streams
        )

        return {
            "total_streams": len(streams),
            "unique_users": unique_users,
            "total_bandwidth_gb": round(total_bandwidth_mb / 1024, 2),
            "avg_bandwidth_mbps": round(avg_bandwidth, 2),
            "min_bandwidth_mbps": round(min_bandwidth, 2),
            "peak_individual_bandwidth_mbps": round(peak_individual_bandwidth, 2),
            "peak_combined_bandwidth_mbps": round(peak_combined_bandwidth, 2),
            "avg_stream_duration_minutes": round(total_duration_seconds / len(streams) / 60, 2),
            "total_duration_hours": round(total_duration_seconds / 3600, 2),
            "days": days,
            "most_common_quality": max(
                (s.quality_profile for s in streams if s.quality_profile),
                key=lambda x: sum(1 for s in streams if s.quality_profile == x),
                default="Unknown"
            )
        }

    except Exception as e:
        log_and_raise_500(e, "get stream summary")
