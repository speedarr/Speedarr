"""
Bandwidth API routes for viewing bandwidth metrics and usage.
"""
from fastapi import APIRouter, Depends, Request, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, desc, func
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from datetime import datetime, timedelta, date, timezone
from loguru import logger

from app.api.auth import require_admin
from app.models import User, BandwidthMetric, BandwidthMetricHourly, BandwidthMetricDaily
from app.database import get_db
from app.utils.bandwidth import filter_streams_for_bandwidth
from app.utils.errors import ErrorCode, raise_error

router = APIRouter(prefix="/api/bandwidth", tags=["bandwidth"])


class TemporaryLimitRequest(BaseModel):
    """Request model for setting temporary bandwidth limits."""
    download_mbps: Optional[float] = Field(None, ge=0, le=100000, description="Download limit in Mbps")
    upload_mbps: Optional[float] = Field(None, ge=0, le=100000, description="Upload limit in Mbps")
    duration_hours: float = Field(
        ...,
        gt=0,
        le=168,  # Max 7 days
        description="Duration in hours (min: >0, max: 168 = 7 days). Use 0.5 for 30 minutes."
    )
    source: Optional[str] = Field(None, max_length=200, description="Source identifier (e.g., 'Home Assistant - Gaming PC')")


class TemporaryLimitResponse(BaseModel):
    """Response model for temporary bandwidth limits."""
    active: bool
    download_mbps: Optional[float] = None
    upload_mbps: Optional[float] = None
    expires_at: Optional[str] = None
    remaining_minutes: Optional[float] = None
    source: Optional[str] = None
    set_by: Optional[str] = None


@router.get("/current")
async def get_current_bandwidth(request: Request):
    """
    Get current real-time bandwidth allocation and usage.

    Returns current throttle state and active stream bandwidth.
    """
    try:
        decision_engine = request.app.state.decision_engine
        polling_monitor = request.app.state.polling_monitor
        controller_manager = request.app.state.controller_manager

        # Get active streams (use bitrate - media file's encoded rate)
        active_streams = polling_monitor._cached_streams or []
        total_stream_bandwidth = sum(s.get("stream_bitrate_mbps", 0) for s in active_streams)

        # Get reserved bandwidth
        reserved_bandwidth = await polling_monitor.get_total_reserved_bandwidth()

        # Get configuration limits
        config = decision_engine.config

        # Filter streams for reserved bandwidth based on LAN/WAN config
        bandwidth_streams = filter_streams_for_bandwidth(
            active_streams, config.plex.include_lan_streams
        )
        reserved_stream_bandwidth = sum(s.get("stream_bitrate_mbps", 0) for s in bandwidth_streams)

        # Get current client stats
        client_stats = await controller_manager.get_client_stats()

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "download": {
                "total_limit_mbps": config.bandwidth.download.total_limit,
                "qbittorrent_limit_mbps": client_stats.get("qbittorrent", {}).get("download_limit"),
                "sabnzbd_limit_mbps": client_stats.get("sabnzbd", {}).get("download_limit"),
                "allocated_mbps": sum(
                    client_stats.get(client, {}).get("download_limit", 0)
                    for client in ["qbittorrent", "sabnzbd"]
                )
            },
            "upload": {
                "total_limit_mbps": config.bandwidth.upload.total_limit,
                "qbittorrent_limit_mbps": client_stats.get("qbittorrent", {}).get("upload_limit"),
                "reserved_for_streams_mbps": reserved_stream_bandwidth,
                "reserved_for_reservations_mbps": reserved_bandwidth
            },
            "streams": {
                "active_count": len(active_streams),
                "total_bandwidth_mbps": total_stream_bandwidth,
                "reserved_bandwidth_mbps": reserved_stream_bandwidth
            }
        }

    except Exception as e:
        logger.error(f"Error getting current bandwidth: {e}")
        raise_error(ErrorCode.INTERNAL_ERROR, "Failed to get current bandwidth", log=False)


@router.get("/history")
async def get_bandwidth_history(
    hours: float = Query(24, ge=0.5, le=168, description="Number of hours to retrieve (min 0.5 for 30 minutes)"),
    granularity: str = Query("5min", description="Data granularity: 5min, hourly, daily"),
    metric_type: Optional[str] = Query(None, description="Filter by metric type"),
    db: AsyncSession = Depends(get_db),
):
    """
    Get historical bandwidth metrics.

    Supports different granularity levels and filtering.
    """
    try:
        # Choose appropriate table based on granularity
        if granularity == "hourly":
            model = BandwidthMetricHourly
            time_filter = model.hour_start >= datetime.now(timezone.utc) - timedelta(hours=hours)
        elif granularity == "daily":
            model = BandwidthMetricDaily
            days = hours // 24 or 1
            time_filter = model.day_date >= date.today() - timedelta(days=days)
        else:
            # 5-minute granularity
            model = BandwidthMetric
            time_filter = model.timestamp >= datetime.now(timezone.utc) - timedelta(hours=hours)

        # Build query
        query = select(model).where(time_filter)

        # Order by time descending
        if granularity == "hourly":
            query = query.order_by(desc(model.hour_timestamp))
        elif granularity == "daily":
            query = query.order_by(desc(model.date))
        else:
            query = query.order_by(desc(model.timestamp))

        # Execute
        result = await db.execute(query.limit(1000))
        metrics = result.scalars().all()

        # Convert to dict
        metrics_list = []
        for m in metrics:
            if hasattr(m, 'timestamp'):
                # 5-minute granularity - return all columns
                item = {
                    "timestamp": m.timestamp.isoformat(),
                    "total_download_limit": m.total_download_limit,
                    "qbittorrent_download_speed": m.qbittorrent_download_speed,
                    "qbittorrent_download_limit": m.qbittorrent_download_limit,
                    "sabnzbd_download_speed": m.sabnzbd_download_speed,
                    "sabnzbd_download_limit": m.sabnzbd_download_limit,
                    "total_upload_limit": m.total_upload_limit,
                    "qbittorrent_upload_speed": m.qbittorrent_upload_speed,
                    "qbittorrent_upload_limit": m.qbittorrent_upload_limit,
                    "sabnzbd_upload_speed": m.sabnzbd_upload_speed,
                    "sabnzbd_upload_limit": m.sabnzbd_upload_limit,
                    "snmp_download_speed": m.snmp_download_speed,
                    "snmp_upload_speed": m.snmp_upload_speed,
                    "active_streams_count": m.active_streams_count,
                    "total_stream_bandwidth": m.total_stream_bandwidth,
                    "is_throttled": m.is_throttled
                }
            elif hasattr(m, 'hour_timestamp'):
                # Hourly aggregates
                item = {
                    "hour_timestamp": m.hour_timestamp.isoformat(),
                    "avg_download_speed": m.avg_download_speed,
                    "avg_upload_speed": m.avg_upload_speed,
                    "avg_active_streams": m.avg_active_streams,
                    "max_download_speed": m.max_download_speed,
                    "max_upload_speed": m.max_upload_speed,
                    "max_active_streams": m.max_active_streams,
                    "minutes_throttled": m.minutes_throttled
                }
            elif hasattr(m, 'date'):
                # Daily aggregates
                item = {
                    "date": m.date.isoformat(),
                    "avg_download_speed": m.avg_download_speed,
                    "avg_upload_speed": m.avg_upload_speed,
                    "avg_active_streams": m.avg_active_streams,
                    "max_download_speed": m.max_download_speed,
                    "max_upload_speed": m.max_upload_speed,
                    "max_active_streams": m.max_active_streams,
                    "total_streams": m.total_streams,
                    "total_throttle_events": m.total_throttle_events,
                    "hours_throttled": m.hours_throttled
                }
            else:
                continue

            metrics_list.append(item)

        return {
            "metrics": metrics_list,
            "total": len(metrics_list),
            "hours": hours,
            "granularity": granularity
        }

    except Exception as e:
        logger.error(f"Error getting bandwidth history: {e}")
        raise_error(ErrorCode.INTERNAL_ERROR, "Failed to get bandwidth history", log=False)


@router.get("/summary")
async def get_bandwidth_summary(
    days: int = Query(7, ge=1, le=90, description="Number of days for summary"),
    db: AsyncSession = Depends(get_db),
):
    """
    Get bandwidth usage summary statistics.

    Provides aggregated bandwidth metrics over a time period.
    """
    try:
        # Get daily metrics for the period
        result = await db.execute(
            select(BandwidthMetricDaily).where(
                BandwidthMetricDaily.date >= date.today() - timedelta(days=days)
            )
        )
        daily_metrics = result.scalars().all()

        if not daily_metrics:
            return {
                "days": days,
                "total_metrics": 0,
                "message": "No bandwidth data available for this period"
            }

        # Calculate aggregate statistics
        return {
            "days": days,
            "total_metrics": len(daily_metrics),
            "download": {
                "avg_speed_mbps": round(sum(m.avg_download_speed or 0 for m in daily_metrics) / len(daily_metrics), 2) if daily_metrics else 0,
                "max_speed_mbps": round(max((m.max_download_speed or 0 for m in daily_metrics), default=0), 2),
            },
            "upload": {
                "avg_speed_mbps": round(sum(m.avg_upload_speed or 0 for m in daily_metrics) / len(daily_metrics), 2) if daily_metrics else 0,
                "max_speed_mbps": round(max((m.max_upload_speed or 0 for m in daily_metrics), default=0), 2),
            },
            "streams": {
                "avg_active": round(sum(m.avg_active_streams or 0 for m in daily_metrics) / len(daily_metrics), 2) if daily_metrics else 0,
                "max_active": max((m.max_active_streams or 0 for m in daily_metrics), default=0),
                "total_streams": sum(m.total_streams or 0 for m in daily_metrics),
            },
            "throttling": {
                "total_events": sum(m.total_throttle_events or 0 for m in daily_metrics),
                "hours_throttled": round(sum(m.hours_throttled or 0 for m in daily_metrics), 2),
            },
            "period_start": (date.today() - timedelta(days=days)).isoformat(),
            "period_end": date.today().isoformat()
        }

    except Exception as e:
        logger.error(f"Error getting bandwidth summary: {e}")
        raise_error(ErrorCode.INTERNAL_ERROR, "Failed to get bandwidth summary", log=False)


@router.get("/chart-data")
async def get_bandwidth_chart_data(
    hours: float = Query(24, ge=0.5, le=168, description="Number of hours to retrieve (min 0.5 for 30 minutes)"),
    interval_minutes: float = Query(5, ge=0.5, le=60, description="Interval in minutes (min 0.5 for 30 seconds)"),
    db: AsyncSession = Depends(get_db),
):
    """
    Get bandwidth data formatted for charting/graphing.

    Returns time-series data suitable for visualization.
    """
    try:
        # Get 5-minute granularity metrics
        result = await db.execute(
            select(BandwidthMetric).where(
                BandwidthMetric.timestamp >= datetime.now(timezone.utc) - timedelta(hours=hours)
            ).order_by(BandwidthMetric.timestamp)
        )
        metrics = result.scalars().all()

        # Convert to chart data format with per-datapoint limits
        chart_data = []

        for m in metrics:
            chart_data.append({
                "timestamp": m.timestamp.isoformat() + 'Z',  # Add Z to indicate UTC
                "download_speed": sum(filter(None, [
                    m.qbittorrent_download_speed, m.sabnzbd_download_speed,
                    m.nzbget_download_speed, m.transmission_download_speed, m.deluge_download_speed
                ])),
                "upload_speed": sum(filter(None, [
                    m.qbittorrent_upload_speed, m.transmission_upload_speed, m.deluge_upload_speed
                ])),
                "stream_bandwidth": m.total_stream_bandwidth or 0,
                "plex_bandwidth": m.total_stream_actual_bandwidth or 0,
                # Per-client download speeds
                "qbittorrent_speed": m.qbittorrent_download_speed or 0,
                "sabnzbd_speed": m.sabnzbd_download_speed or 0,
                "nzbget_speed": m.nzbget_download_speed or 0,
                "transmission_speed": m.transmission_download_speed or 0,
                "deluge_speed": m.deluge_download_speed or 0,
                # Per-client upload speeds
                "qbittorrent_upload_speed": m.qbittorrent_upload_speed or 0,
                "transmission_upload_speed": m.transmission_upload_speed or 0,
                "deluge_upload_speed": m.deluge_upload_speed or 0,
                # Per-client download limits
                "qbittorrent_download_limit": m.qbittorrent_download_limit,
                "sabnzbd_download_limit": m.sabnzbd_download_limit,
                "nzbget_download_limit": m.nzbget_download_limit,
                "transmission_download_limit": m.transmission_download_limit,
                "deluge_download_limit": m.deluge_download_limit,
                # Per-client upload limits
                "qbittorrent_upload_limit": m.qbittorrent_upload_limit,
                "transmission_upload_limit": m.transmission_upload_limit,
                "deluge_upload_limit": m.deluge_upload_limit,
                # Other
                "active_streams_count": m.active_streams_count or 0,
                "snmp_download_speed": m.snmp_download_speed,
                "snmp_upload_speed": m.snmp_upload_speed,
            })

        return {
            "data": chart_data,
            "start_time": chart_data[0]["timestamp"] if chart_data else (datetime.now(timezone.utc).isoformat() + 'Z'),
            "end_time": chart_data[-1]["timestamp"] if chart_data else (datetime.now(timezone.utc).isoformat() + 'Z'),
            "interval_minutes": interval_minutes,
        }

    except Exception as e:
        logger.error(f"Error getting chart data: {e}")
        raise_error(ErrorCode.INTERNAL_ERROR, "Failed to get chart data", log=False)


@router.get("/temporary-limits", response_model=TemporaryLimitResponse)
async def get_temporary_limits(request: Request):
    """
    Get current temporary bandwidth limits if active.
    """
    try:
        polling_monitor = request.app.state.polling_monitor

        # Use lock for thread-safe access to temporary limits
        async with polling_monitor._temporary_limits_lock:
            temp_limits = getattr(polling_monitor, '_temporary_limits', None)

            if temp_limits and temp_limits.get('expires_at'):
                expires_at = temp_limits['expires_at']
                now = datetime.now(timezone.utc)

                if expires_at > now:
                    remaining = (expires_at - now).total_seconds() / 60
                    return TemporaryLimitResponse(
                        active=True,
                        download_mbps=temp_limits.get('download_mbps'),
                        upload_mbps=temp_limits.get('upload_mbps'),
                        expires_at=expires_at.isoformat() + 'Z',
                        remaining_minutes=round(remaining, 1),
                        source=temp_limits.get('source'),
                        set_by=temp_limits.get('set_by'),
                    )

        return TemporaryLimitResponse(active=False)

    except Exception as e:
        logger.error(f"Error getting temporary limits: {e}")
        raise_error(ErrorCode.INTERNAL_ERROR, "Failed to get temporary limits", log=False)


@router.post("/temporary-limits", response_model=TemporaryLimitResponse)
async def set_temporary_limits(
    request: Request,
    limits: TemporaryLimitRequest,
    current_user: User = Depends(require_admin)
):
    """
    Set temporary bandwidth limits for a specified duration.

    The limits will override normal bandwidth calculations until they expire.
    """
    try:
        polling_monitor = request.app.state.polling_monitor

        # Pydantic validates duration_hours > 0 and <= 168 hours (7 days)
        expires_at = datetime.now(timezone.utc) + timedelta(hours=limits.duration_hours)

        # Use API key name when authenticated via API key
        api_key_name = getattr(request.state, 'api_key_name', None)
        set_by = f"API: {api_key_name}" if api_key_name else current_user.username

        # Use lock for thread-safe access to temporary limits
        async with polling_monitor._temporary_limits_lock:
            polling_monitor._temporary_limits = {
                'download_mbps': limits.download_mbps,
                'upload_mbps': limits.upload_mbps,
                'expires_at': expires_at,
                'set_by': set_by,
                'set_at': datetime.now(timezone.utc),
                'source': limits.source,
            }

        remaining = limits.duration_hours * 60

        source_info = f", source='{limits.source}'" if limits.source else ""
        logger.info(
            f"Temporary limits set by {set_by}: "
            f"download={limits.download_mbps} Mbps, upload={limits.upload_mbps} Mbps, "
            f"expires in {limits.duration_hours} hours{source_info}"
        )

        return TemporaryLimitResponse(
            active=True,
            download_mbps=limits.download_mbps,
            upload_mbps=limits.upload_mbps,
            expires_at=expires_at.isoformat() + 'Z',
            remaining_minutes=round(remaining, 1),
            source=limits.source,
            set_by=set_by,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting temporary limits: {e}")
        raise_error(ErrorCode.INTERNAL_ERROR, "Failed to set temporary limits", log=False)


@router.delete("/temporary-limits")
async def clear_temporary_limits(
    request: Request,
    current_user: User = Depends(require_admin)
):
    """
    Clear any active temporary bandwidth limits.
    """
    try:
        polling_monitor = request.app.state.polling_monitor

        # Use lock for thread-safe access to temporary limits
        async with polling_monitor._temporary_limits_lock:
            if hasattr(polling_monitor, '_temporary_limits'):
                polling_monitor._temporary_limits = None
                logger.info(f"Temporary limits cleared by {current_user.username}")

        return {"message": "Temporary limits cleared", "active": False}

    except Exception as e:
        logger.error(f"Error clearing temporary limits: {e}")
        raise_error(ErrorCode.INTERNAL_ERROR, "Failed to clear temporary limits", log=False)


@router.get("/reservations")
async def get_reservations(request: Request):
    """
    Get list of active bandwidth reservations.

    Reservations hold bandwidth for a period after streams end.
    """
    try:
        polling_monitor = request.app.state.polling_monitor
        reservations = await polling_monitor.get_reservations()

        return {
            "reservations": reservations,
            "total_reserved_mbps": await polling_monitor.get_total_reserved_bandwidth(),
            "count": len(reservations)
        }

    except Exception as e:
        logger.error(f"Error getting reservations: {e}")
        raise_error(ErrorCode.INTERNAL_ERROR, "Failed to get reservations", log=False)


@router.delete("/reservations/{reservation_id}")
async def clear_reservation(
    reservation_id: str,
    request: Request,
    current_user: User = Depends(require_admin)
):
    """
    Clear a specific bandwidth reservation.

    Args:
        reservation_id: The unique ID of the reservation to clear
    """
    try:
        polling_monitor = request.app.state.polling_monitor
        success = await polling_monitor.clear_reservation_by_id(reservation_id)

        if not success:
            raise_error(ErrorCode.NOT_FOUND, "Reservation not found", status_code=404)

        logger.info(f"Reservation {reservation_id} cleared by {current_user.username}")

        return {
            "message": "Reservation cleared",
            "reservation_id": reservation_id
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error clearing reservation: {e}")
        raise_error(ErrorCode.INTERNAL_ERROR, "Failed to clear reservation", log=False)
