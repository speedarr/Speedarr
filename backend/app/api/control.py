"""
Control API routes for manual overrides.
"""
from fastapi import APIRouter, Depends, Request, HTTPException
from pydantic import BaseModel
from typing import Optional
from loguru import logger

from app.api.auth import require_admin
from app.models import User
from app.utils.errors import ErrorCode, raise_error

router = APIRouter(prefix="/api/control", tags=["control"])


class ManualThrottleRequest(BaseModel):
    qbittorrent_download_limit: Optional[float] = None
    qbittorrent_upload_limit: Optional[float] = None
    sabnzbd_download_limit: Optional[float] = None
    sabnzbd_upload_limit: Optional[float] = None
    duration_minutes: Optional[int] = None
    reason: str = "Manual throttle"


class RestoreSpeedsRequest(BaseModel):
    reason: str = "Manual restoration"


@router.post("/restore-speeds")
async def restore_speeds(
    request: Request,
    body: RestoreSpeedsRequest = RestoreSpeedsRequest(),
    current_user: User = Depends(require_admin)
):
    """
    Manually restore all download/upload speeds to normal.

    This overrides any active throttling.
    """
    try:
        controller_manager = request.app.state.controller_manager
        notification_service = request.app.state.notification_service

        # Restore speeds for all clients
        results = await controller_manager.restore_all_speeds()

        # Send notification
        await notification_service.notify(
            "speeds_manually_overridden",
            f"Speeds manually restored by {current_user.username}",
            {"user": current_user.username, "reason": body.reason}
        )

        # TODO: Record decision in database

        # Get current stats after restoration
        stats = await controller_manager.get_client_stats()

        return {
            "message": "Speeds restored successfully",
            "results": results,
            "clients": stats,
            "restored_by": current_user.username
        }

    except Exception as e:
        logger.error(f"Error restoring speeds: {e}")
        raise_error(ErrorCode.INTERNAL_ERROR, "Failed to restore speeds", log=False)


@router.post("/manual-throttle")
async def manual_throttle(
    request: Request,
    body: ManualThrottleRequest,
    current_user: User = Depends(require_admin)
):
    """
    Manually apply specific speed limits to download clients.

    This overrides automatic throttling.
    """
    try:
        controller_manager = request.app.state.controller_manager
        notification_service = request.app.state.notification_service

        # Build decisions dict
        decisions = {}

        if body.qbittorrent_download_limit is not None or body.qbittorrent_upload_limit is not None:
            decisions["qbittorrent"] = {
                "action": "throttle",
                "download_limit": body.qbittorrent_download_limit,
                "upload_limit": body.qbittorrent_upload_limit,
                "reason": body.reason
            }

        if body.sabnzbd_download_limit is not None or body.sabnzbd_upload_limit is not None:
            decisions["sabnzbd"] = {
                "action": "throttle",
                "download_limit": body.sabnzbd_download_limit,
                "upload_limit": body.sabnzbd_upload_limit,
                "reason": body.reason
            }

        if not decisions:
            raise_error(ErrorCode.VALIDATION_ERROR, "No speed limits specified", status_code=400)

        # Apply throttling
        results = await controller_manager.apply_decisions(decisions)

        # Send notification
        await notification_service.notify(
            "speeds_manually_overridden",
            f"Manual throttle applied by {current_user.username}: {body.reason}",
            {"user": current_user.username, "decisions": decisions}
        )

        # TODO: Record decision in database with manual flag

        return {
            "message": "Manual throttle applied",
            "results": results,
            "decisions": decisions,
            "applied_by": current_user.username,
            "duration_minutes": body.duration_minutes
        }

    except Exception as e:
        logger.error(f"Error applying manual throttle: {e}")
        raise_error(ErrorCode.INTERNAL_ERROR, "Failed to apply manual throttle", log=False)


@router.post("/pause-monitoring")
async def pause_monitoring(
    request: Request,
    duration_minutes: int = 30,
    restore_speeds: bool = True,
    current_user: User = Depends(require_admin)
):
    """
    Temporarily pause all monitoring and throttling.

    Useful for maintenance or troubleshooting.
    """
    try:
        polling_monitor = request.app.state.polling_monitor
        controller_manager = request.app.state.controller_manager

        # Restore speeds if requested
        if restore_speeds:
            await controller_manager.restore_all_speeds()

        # TODO: Implement pause mechanism
        # For now, just restore speeds and log

        logger.warning(f"Monitoring pause requested by {current_user.username} for {duration_minutes}min")

        return {
            "message": "Monitoring paused",
            "duration_minutes": duration_minutes,
            "speeds_restored": restore_speeds,
            "paused_by": current_user.username
        }

    except Exception as e:
        logger.error(f"Error pausing monitoring: {e}")
        raise_error(ErrorCode.INTERNAL_ERROR, "Failed to pause monitoring", log=False)


@router.post("/resume-monitoring")
async def resume_monitoring(
    request: Request,
    current_user: User = Depends(require_admin)
):
    """
    Resume monitoring if paused.
    """
    try:
        # TODO: Implement resume mechanism

        logger.info(f"Monitoring resumed by {current_user.username}")

        return {
            "message": "Monitoring resumed",
            "resumed_by": current_user.username
        }

    except Exception as e:
        logger.error(f"Error resuming monitoring: {e}")
        raise_error(ErrorCode.INTERNAL_ERROR, "Failed to resume monitoring", log=False)
