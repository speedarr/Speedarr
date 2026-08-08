"""
Status API routes.
"""
from datetime import datetime
from fastapi import APIRouter, Query, Request, Depends
from loguru import logger
from app import __version__, __commit__, __branch__
from app.api.auth import require_auth_if_private
from app.utils.bandwidth import calculate_stream_bandwidth, filter_streams_for_bandwidth, split_stream_bitrate_by_network
from app.services.decision_engine import is_within_schedule
from app.services.version_service import version_checker

router = APIRouter(prefix="/api/status", tags=["status"])


@router.get("/current")
async def get_current_status(request: Request, _auth=Depends(require_auth_if_private)):
    """Get current system status."""
    # Check if setup is required
    setup_flag = getattr(request.app.state, 'setup_required', False)
    has_config = request.app.state.config is not None
    logger.debug(f"status/current: setup_required={setup_flag}, has_config={has_config}")
    if setup_flag or not has_config:
        return {
            "status": "setup_required",
            "setup_required": True,
            "active_streams": 0,
            "is_throttled": False,
            "throttling_enabled": True,
            "throttling_disabled_until": None,
            "throttling_disabled_by": None,
            "bandwidth": {
                "download": {"total_limit": 0, "current_usage": 0, "clients": []},
                "upload": {"total_limit": 0, "current_usage": 0, "clients": []},
            },
        }

    controller_manager = request.app.state.controller_manager
    polling_monitor = request.app.state.polling_monitor
    config = request.app.state.config

    # Use cached client stats from polling monitor (avoids blocking on unreachable clients)
    download_stats = polling_monitor._cached_client_stats

    # Get enabled download clients config
    enabled_clients = config.get_enabled_download_clients()

    # Get active streams from polling monitor
    active_streams = polling_monitor._cached_streams or []

    # Calculate total stream bandwidth (raw) - shows ALL streams for display
    # Use bitrate (media file's encoded rate) instead of bandwidth (network throughput)
    total_stream_bandwidth = sum(
        stream.get("stream_bitrate_mbps", 0) for stream in active_streams
    )

    # Split stream bitrate into WAN/LAN for the WAN-focused dashboard card
    wan_stream_bandwidth, lan_stream_bandwidth = split_stream_bitrate_by_network(active_streams)

    # Filter streams for bandwidth calculation based on LAN/WAN config
    bandwidth_streams = filter_streams_for_bandwidth(active_streams)

    # Calculate reserved bandwidth (with overhead, or fixed manual value) - only counts WAN streams when toggle is off
    streams_config = config.bandwidth.streams
    reserved_bandwidth = sum(
        calculate_stream_bandwidth(
            stream,
            streams_config.overhead_percent,
            bandwidth_calculation=streams_config.bandwidth_calculation,
            manual_per_stream=streams_config.manual_per_stream,
        )
        for stream in bandwidth_streams
    )

    # Get holding bandwidth (from ended streams in restoration delay period)
    holding_bandwidth = await polling_monitor.get_total_reserved_bandwidth() if hasattr(polling_monitor, 'get_total_reserved_bandwidth') else 0

    # Calculate download reserve for TCP ACKs/control traffic
    download_reserve_percent = config.bandwidth.streams.download_reserve_percent
    download_stream_reserve = reserved_bandwidth * (download_reserve_percent / 100) if download_reserve_percent > 0 else 0
    download_holding_reserve = holding_bandwidth * (download_reserve_percent / 100) if download_reserve_percent > 0 else 0

    # Calculate current usage from all clients (now keyed by client ID)
    total_download_usage = sum(
        download_stats.get(c.id, {}).get("download_speed", 0) or 0
        for c in enabled_clients
    )
    total_upload_usage = sum(
        download_stats.get(c.id, {}).get("upload_speed", 0) or 0
        for c in enabled_clients
    ) + total_stream_bandwidth  # Add Plex stream bandwidth

    # Get SNMP data if available
    snmp_download = None
    snmp_upload = None
    if hasattr(polling_monitor, '_last_snmp_data') and polling_monitor._last_snmp_data:
        snmp_download = polling_monitor._last_snmp_data.get('download')
        snmp_upload = polling_monitor._last_snmp_data.get('upload')

    # Build dynamic client data for download (use client ID for stats lookup)
    download_clients = []
    for client_config in enabled_clients:
        stats = download_stats.get(client_config.id, {})
        download_clients.append({
            "id": client_config.id,
            "type": client_config.type,
            "name": client_config.name,
            "color": client_config.color,
            "speed": stats.get("download_speed", 0) or 0,
            "limit": stats.get("download_limit", 0) or 0,
            "active": stats.get("active", False),
            "error": (stats.get("error") or "Connection failed") if "error" in stats else None,
        })

    # Build dynamic client data for upload (only clients that support upload)
    upload_clients = []
    for client_config in enabled_clients:
        if client_config.supports_upload:
            stats = download_stats.get(client_config.id, {})
            upload_clients.append({
                "id": client_config.id,
                "type": client_config.type,
                "name": client_config.name,
                "color": client_config.color,
                "speed": stats.get("upload_speed", 0) or 0,
                "limit": stats.get("upload_limit", 0) or 0,
                "active": stats.get("active", False),
                "error": (stats.get("error") or "Connection failed") if "error" in stats else None,
            })

    # Calculate effective total limits (use scheduled if in schedule window)
    download_in_schedule = is_within_schedule(config.bandwidth.download.scheduled)
    upload_in_schedule = is_within_schedule(config.bandwidth.upload.scheduled)

    effective_download_limit = (
        config.bandwidth.download.scheduled.total_limit
        if download_in_schedule and config.bandwidth.download.scheduled.total_limit > 0
        else config.bandwidth.download.total_limit
    )
    effective_upload_limit = (
        config.bandwidth.upload.scheduled.total_limit
        if upload_in_schedule and config.bandwidth.upload.scheduled.total_limit > 0
        else config.bandwidth.upload.total_limit
    )

    # Check if SNMP is enabled in config
    snmp_enabled = config.snmp.enabled if hasattr(config, 'snmp') and config.snmp else False

    media_server_statuses = {}
    for s in config.get_all_media_servers():
        st = getattr(polling_monitor, "_server_state", {}).get(s.id, {})
        media_server_statuses[s.id] = {
            "connected": st.get("failures", 0) == 0,
            "consecutive_failures": st.get("failures", 0),
            "type": s.type,
            "name": s.name,
        }

    return {
        "status": "running",
        "setup_required": False,
        "active_streams": len(active_streams),
        "is_throttled": len(active_streams) > 0,
        **polling_monitor.get_throttling_status(),
        "snmp_enabled": snmp_enabled,
        "media_server_statuses": media_server_statuses,
        "snmp_status": {
            "enabled": snmp_enabled,
            "connected": polling_monitor._last_snmp_data is not None if snmp_enabled else True,
        },
        "bandwidth": {
            "download": {
                "total_limit": effective_download_limit,
                "current_usage": total_download_usage,
                "clients": download_clients,  # New dynamic client data
                # Download reserve for TCP ACKs from Plex streams
                "stream_reserve": download_stream_reserve,
                "holding_reserve": download_holding_reserve,
                "snmp_speed": snmp_download,
                "available": max(0, effective_download_limit - total_download_usage - download_stream_reserve - download_holding_reserve),
                "scheduled_active": download_in_schedule,
            },
            "upload": {
                "total_limit": effective_upload_limit,
                "current_usage": total_upload_usage,
                "clients": upload_clients,  # New dynamic client data
                "snmp_speed": snmp_upload,
                "available": max(0, effective_upload_limit - reserved_bandwidth - holding_bandwidth),
                "stream_bandwidth": total_stream_bandwidth,
                "wan_stream_bandwidth": wan_stream_bandwidth,
                "lan_stream_bandwidth": lan_stream_bandwidth,
                "reserved_bandwidth": reserved_bandwidth,
                "holding_bandwidth": holding_bandwidth,
                "scheduled_active": upload_in_schedule,
            },
        },
    }


@router.get("/version")
async def get_version_info(force_refresh: bool = Query(False)):
    """Check current version and whether an update is available."""
    result = await version_checker.check_for_updates(
        __version__, current_commit=__commit__, current_branch=__branch__, force_refresh=force_refresh
    )
    return {
        "current_version": __version__,
        "current_commit": __commit__,
        "current_branch": __branch__,
        "update_available": result.get("update_available", False),
        "latest_version": result.get("latest_version"),
        "latest_commit": result.get("latest_commit"),
        "release_url": result.get("release_url"),
        "error": result.get("error"),
    }
