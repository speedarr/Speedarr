"""
Control API routes for manual overrides.
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List
from loguru import logger

from app.api.auth import require_admin
from app.models import User
from app.utils.errors import ErrorCode, raise_error
from app.database import AsyncSessionLocal
from app.services.throttling_state import save_throttling_disabled, clear_throttling_state

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
        polling_monitor = getattr(request.app.state, "polling_monitor", None)
        if polling_monitor is not None and not polling_monitor.is_throttling_enabled():
            raise_error(
                ErrorCode.VALIDATION_ERROR,
                "Speedarr throttling is disabled",
                status_code=409,
            )

        controller_manager = request.app.state.controller_manager
        notification_service = request.app.state.notification_service

        # Build id-keyed decisions; reject empty or unknown clients.
        known_ids = set(controller_manager.clients.keys())
        try:
            decisions = build_throttle_decisions(body.clients, known_ids, body.reason)
        except ValueError as e:
            raise_error(ErrorCode.VALIDATION_ERROR, str(e), status_code=400)

        # Apply throttling
        results = await controller_manager.apply_decisions(
            decisions,
            abort_if=lambda: polling_monitor is not None and not polling_monitor.is_throttling_enabled(),
        )

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


class PauseMonitoringRequest(BaseModel):
    duration_minutes: Optional[int] = Field(None, ge=1, le=10080)


@router.post("/pause-monitoring")
async def pause_monitoring(
    request: Request,
    body: PauseMonitoringRequest = PauseMonitoringRequest(),
    current_user: User = Depends(require_admin)
):
    """
    Disable throttling: set all client limits to unlimited and stop applying decisions.
    Polling and the dashboard stay live. Omit duration_minutes for indefinite.
    Calling while already disabled replaces the window (last write wins).
    """
    polling_monitor = request.app.state.polling_monitor
    controller_manager = request.app.state.controller_manager
    if polling_monitor is None or controller_manager is None:
        raise_error(ErrorCode.VALIDATION_ERROR, "Speedarr is not configured yet", status_code=400)

    until = (
        datetime.now(timezone.utc) + timedelta(minutes=body.duration_minutes)
        if body.duration_minutes else None
    )

    try:
        # Persist first - memory only updates after a durable write.
        async with AsyncSessionLocal() as db:
            await save_throttling_disabled(db, until=until, by=current_user.username)
            await db.commit()
        await polling_monitor.set_throttling_state(True, until, current_user.username)

        restore_results = await controller_manager.remove_all_limits()

        logger.info(
            f"Throttling disabled by {current_user.username}"
            + (f" until {until.isoformat()}" if until else " indefinitely")
            + " - all client limits removed"
        )
        return {
            "message": "Throttling disabled",
            "throttling_enabled": False,
            "throttling_disabled_until": until.isoformat() if until else None,
            "throttling_disabled_by": current_user.username,
            "restore_results": restore_results,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error disabling throttling: {e}")
        raise_error(ErrorCode.INTERNAL_ERROR, "Failed to disable throttling", log=False)


@router.post("/resume-monitoring")
async def resume_monitoring(
    request: Request,
    current_user: User = Depends(require_admin)
):
    """Re-enable throttling. Idempotent when already enabled."""
    polling_monitor = request.app.state.polling_monitor
    if polling_monitor is None:
        raise_error(ErrorCode.VALIDATION_ERROR, "Speedarr is not configured yet", status_code=400)

    try:
        async with AsyncSessionLocal() as db:
            await clear_throttling_state(db)
            await db.commit()
        await polling_monitor.set_throttling_state(False, None, None)

        logger.info(f"Throttling re-enabled by {current_user.username}")
        return {
            "message": "Throttling enabled",
            "throttling_enabled": True,
            "throttling_disabled_until": None,
            "throttling_disabled_by": None,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error re-enabling throttling: {e}")
        raise_error(ErrorCode.INTERNAL_ERROR, "Failed to re-enable throttling", log=False)
