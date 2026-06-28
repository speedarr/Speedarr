"""
Control API routes for manual overrides.
"""
from fastapi import APIRouter, Depends, Request, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from loguru import logger

from app.api.auth import require_admin
from app.models import User
from app.utils.errors import ErrorCode, raise_error

router = APIRouter(prefix="/api/control", tags=["control"])


class ClientThrottle(BaseModel):
    client_id: str
    download_limit: Optional[float] = None
    upload_limit: Optional[float] = None


class ManualThrottleRequest(BaseModel):
    clients: List[ClientThrottle]
    duration_minutes: Optional[int] = None
    reason: str = "Manual throttle"


def build_throttle_decisions(clients, known_ids, reason: str) -> dict:
    """Build an id-keyed decisions dict for controller_manager.apply_decisions.

    Raises ValueError if the list is empty or names an unknown client id.
    """
    if not clients:
        raise ValueError("No clients specified")
    decisions = {}
    for ct in clients:
        if ct.client_id not in known_ids:
            raise ValueError(f"Unknown client: {ct.client_id}")
        decisions[ct.client_id] = {
            "action": "throttle",
            "download_limit": ct.download_limit,
            "upload_limit": ct.upload_limit,
            "reason": reason,
        }
    return decisions


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

        # Build id-keyed decisions; reject empty or unknown clients.
        known_ids = set(controller_manager.clients.keys())
        try:
            decisions = build_throttle_decisions(body.clients, known_ids, body.reason)
        except ValueError as e:
            raise_error(ErrorCode.VALIDATION_ERROR, str(e), status_code=400)

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

    except HTTPException:
        raise
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
