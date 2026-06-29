"""
Bandwidth API routes for viewing bandwidth metrics and usage.
"""
import json
from fastapi import APIRouter, Depends, Request, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, desc, func
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List, Dict, Any, Iterable
from datetime import datetime, timedelta, date, timezone
from loguru import logger

from app.api.auth import require_admin
from app.models import User, BandwidthMetric, BandwidthMetricHourly, BandwidthMetricDaily
from app.database import get_db
from app.utils.errors import ErrorCode, raise_error

router = APIRouter(prefix="/api/bandwidth", tags=["bandwidth"])


def pivot_per_server(rows):
    """rows: iterable of (timestamp, per_server_json). Returns (series_ids, points)."""
    series_ids = set()
    points = []
    for ts, raw in rows:
        point = {"timestamp": ts}
        if raw:
            try:
                data = json.loads(raw)
                for sid, mbps in data.items():
                    point[sid] = mbps
                    series_ids.add(sid)
            except (ValueError, TypeError):
                pass
        points.append(point)
    return sorted(series_ids), points


def parse_per_client(raw):
    """Parse a BandwidthMetric.per_client JSON string into {client_id: {d,u,dl,ul}}.

    Tolerant of None and malformed JSON (returns {}), mirroring pivot_per_server.
    """
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def client_series_from_ids(ids):
    """Build the sorted client_series descriptor list from a set of series ids.

    Type is derived by splitting on '_' (client ids are '<type>_<timestamp>';
    legacy series ids equal the bare type).
    """
    return [{"id": sid, "type": sid.split("_")[0]} for sid in sorted(ids)]


class TemporaryLimitRequest(BaseModel):
    """Request model for setting temporary bandwidth limits."""
    download_mbps: Optional[float] = Field(None, ge=0, le=100000, description="Download limit in Mbps")
    upload_mbps: Optional[float] = Field(None, ge=0, le=100000, description="Upload limit in Mbps")
    duration_hours: Optional[float] = Field(
        None,
        gt=0,
        le=168,  # Max 7 days
        description="Duration in hours (min: >0, max: 168 = 7 days). Omit for indefinite (until cleared)."
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
        client_series_ids: set = set()

        for m in metrics:
            point = {
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
                # Other
                "active_streams_count": m.active_streams_count or 0,
                "wan_stream_bandwidth": m.wan_stream_bandwidth,
                "lan_stream_bandwidth": m.lan_stream_bandwidth,
                "wan_streams_count": m.wan_streams_count,
                "lan_streams_count": m.lan_streams_count,
                "snmp_download_speed": m.snmp_download_speed,
                "snmp_upload_speed": m.snmp_upload_speed,
            }

            per_client = parse_per_client(m.per_client)
            if per_client:
                # New row — emit per-client-id fields keyed by client id.
                for cid, vals in per_client.items():
                    point[f"{cid}_speed"] = vals.get("d") or 0
                    point[f"{cid}_upload_speed"] = vals.get("u") or 0
                    point[f"{cid}_download_limit"] = vals.get("dl")
                    point[f"{cid}_upload_limit"] = vals.get("ul")
                    client_series_ids.add(cid)
            else:
                # Legacy row (no per_client) — emit one merged series per type,
                # keyed by the type string (series id == type).
                legacy = [
                    ("qbittorrent", m.qbittorrent_download_speed, m.qbittorrent_upload_speed,
                     m.qbittorrent_download_limit, m.qbittorrent_upload_limit),
                    ("sabnzbd", m.sabnzbd_download_speed, None, m.sabnzbd_download_limit, None),
                    ("nzbget", m.nzbget_download_speed, None, m.nzbget_download_limit, None),
                    ("transmission", m.transmission_download_speed, m.transmission_upload_speed,
                     m.transmission_download_limit, m.transmission_upload_limit),
                    ("deluge", m.deluge_download_speed, m.deluge_upload_speed,
                     m.deluge_download_limit, m.deluge_upload_limit),
                ]
                for t, dl_speed, ul_speed, dl_limit, ul_limit in legacy:
                    if dl_speed is None and ul_speed is None and dl_limit is None and ul_limit is None:
                        continue
                    point[f"{t}_speed"] = dl_speed or 0
                    point[f"{t}_upload_speed"] = ul_speed or 0
                    point[f"{t}_download_limit"] = dl_limit
                    point[f"{t}_upload_limit"] = ul_limit
                    client_series_ids.add(t)

            chart_data.append(point)

        # Build per-server pivot from raw BandwidthMetric rows.
        # v1 limitation: per_server data is only available on raw metrics (this
        # window); hourly/daily rollups do not carry the per_server JSON column.
        server_series, server_points = pivot_per_server(
            [(m.timestamp.isoformat() + 'Z', m.per_server) for m in metrics]
        )

        return {
            "data": chart_data,
            "start_time": chart_data[0]["timestamp"] if chart_data else (datetime.now(timezone.utc).isoformat() + 'Z'),
            "end_time": chart_data[-1]["timestamp"] if chart_data else (datetime.now(timezone.utc).isoformat() + 'Z'),
            "interval_minutes": interval_minutes,
            "per_server_series": server_series,
            "per_server_points": server_points,
            "client_series": client_series_from_ids(client_series_ids),
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

        from app.services.polling_monitor import most_restrictive

        # Manual temporary limit (may be expiring)
        manual_dl, manual_ul, manual_source, manual_set_by = None, None, None, None
        expires_iso, remaining = None, None
        async with polling_monitor._temporary_limits_lock:
            tl = getattr(polling_monitor, "_temporary_limits", None)
            if tl:
                expires_at = tl.get("expires_at")
                now = datetime.now(timezone.utc)
                if expires_at is None or expires_at > now:
                    manual_dl = tl.get("download_mbps")
                    manual_ul = tl.get("upload_mbps")
                    manual_source = tl.get("source")
                    manual_set_by = tl.get("set_by")
                    if expires_at is not None:
                        expires_iso = expires_at.isoformat() + "Z"
                        remaining = round((expires_at - now).total_seconds() / 60, 1)

        # Unraid override (indefinite while a condition is active)
        unraid_dl, unraid_ul, unraid_source = None, None, None
        async with polling_monitor._unraid_override_lock:
            ov = getattr(polling_monitor, "_unraid_override", None)
            if ov:
                unraid_dl = ov.get("download_mbps")
                unraid_ul = ov.get("upload_mbps")
                tag = "unraid:" + ",".join(ov.get("reasons", []))
                if ov.get("holding"):
                    tag += " (holding)"
                unraid_source = tag

        if manual_source is None and unraid_source is None:
            return TemporaryLimitResponse(active=False)

        sources = [s for s in (manual_source, unraid_source) if s]
        return TemporaryLimitResponse(
            active=True,
            download_mbps=most_restrictive(manual_dl, unraid_dl),
            upload_mbps=most_restrictive(manual_ul, unraid_ul),
            expires_at=expires_iso,
            remaining_minutes=remaining,
            source=" + ".join(sources),
            set_by=manual_set_by,
        )

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

        # Compute expiry: None means indefinite (until cleared)
        expires_at = None
        if limits.duration_hours is not None:
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

        remaining = limits.duration_hours * 60 if limits.duration_hours is not None else None

        source_info = f", source='{limits.source}'" if limits.source else ""
        duration_info = f"expires in {limits.duration_hours} hours" if limits.duration_hours is not None else "indefinite (until cleared)"
        logger.info(
            f"Temporary limits set by {set_by}: "
            f"download={limits.download_mbps} Mbps, upload={limits.upload_mbps} Mbps, "
            f"{duration_info}{source_info}"
        )

        return TemporaryLimitResponse(
            active=True,
            download_mbps=limits.download_mbps,
            upload_mbps=limits.upload_mbps,
            expires_at=expires_at.isoformat() + 'Z' if expires_at else None,
            remaining_minutes=round(remaining, 1) if remaining is not None else None,
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
