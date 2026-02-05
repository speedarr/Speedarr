"""
Main FastAPI application for Speedarr.
"""
import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from loguru import logger

from app.config import settings, SpeedarrConfig
from app.middleware.correlation import CorrelationIdMiddleware
from app.constants import (
    TASK_MONITOR_CHECK_INTERVAL_SECONDS,
    RETENTION_CLEANUP_INTERVAL_SECONDS,
    SHUTDOWN_RESTORE_TIMEOUT_SECONDS,
)


def validate_secrets():
    """
    Validate that required secrets are properly configured.
    Logs warnings for missing/weak secrets but allows auto-generation.
    """
    # Check JWT secret
    jwt_env = os.getenv("AUTH__SECRET_KEY")
    jwt_file = Path("/data/.jwt_secret")

    if jwt_env and jwt_env == "change-me-in-production":
        logger.warning("AUTH__SECRET_KEY is set to placeholder value - auto-generating secure key")
    elif jwt_env and len(jwt_env) < 32:
        logger.warning(f"AUTH__SECRET_KEY is weak ({len(jwt_env)} chars) - recommend at least 32 chars")
    elif not jwt_env and not jwt_file.exists():
        logger.info("No JWT secret configured - auto-generating secure key")

    # Check encryption key
    enc_env = os.getenv("CONFIG_ENCRYPTION_KEY")
    enc_file = Path("/data/.encryption_key")

    if not enc_env and not enc_file.exists():
        logger.info("No encryption key configured - auto-generating secure key")
    elif enc_env and len(enc_env) < 32:
        logger.warning(f"CONFIG_ENCRYPTION_KEY appears weak ({len(enc_env)} chars)")

    # Verify data directory is writable (needed for auto-generated keys)
    data_dir = Path("/data")
    if not data_dir.exists():
        try:
            data_dir.mkdir(parents=True, exist_ok=True)
            logger.info("Created /data directory for persistent storage")
        except PermissionError:
            logger.error("Cannot create /data directory - auto-generated secrets will be lost on restart!")
    elif not os.access(data_dir, os.W_OK):
        logger.error("/data directory is not writable - auto-generated secrets will be lost on restart!")
from app.database import init_db, close_db, AsyncSessionLocal
from app.utils.logger import setup_logger
from app.services import DecisionEngine, ControllerManager, PollingMonitor, NotificationService, RetentionService
from app.services.config_manager import ConfigManager
from app.api import auth, status, control, streams, bandwidth, settings as settings_api, decisions

class BackgroundTaskMonitor:
    """
    Monitors and restarts background tasks if they die unexpectedly.
    """

    def __init__(self, app: FastAPI):
        self.app = app
        self._tasks: dict[str, asyncio.Task] = {}
        self._task_factories: dict[str, callable] = {}
        self._monitor_task: asyncio.Task | None = None
        self._running = False

    def register_task(self, name: str, factory: callable) -> asyncio.Task:
        """
        Register and start a background task.

        Args:
            name: Unique name for the task
            factory: Coroutine factory that creates the task

        Returns:
            The created asyncio.Task
        """
        self._task_factories[name] = factory
        task = asyncio.create_task(factory(), name=name)
        self._tasks[name] = task
        logger.info(f"Background task '{name}' started")
        return task

    async def start_monitoring(self, check_interval: float = TASK_MONITOR_CHECK_INTERVAL_SECONDS):
        """Start the task monitor."""
        self._running = True
        self._monitor_task = asyncio.create_task(
            self._monitor_loop(check_interval),
            name="task_monitor"
        )

    async def stop(self):
        """Stop all tasks and the monitor."""
        self._running = False

        # Cancel monitor task
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass

        # Cancel all registered tasks
        for name, task in self._tasks.items():
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            logger.debug(f"Background task '{name}' stopped")

    async def _monitor_loop(self, check_interval: float):
        """Monitor tasks and restart if needed."""
        while self._running:
            try:
                await asyncio.sleep(check_interval)

                for name, task in list(self._tasks.items()):
                    if task.done():
                        # Check if task completed with an exception
                        try:
                            exc = task.exception()
                            if exc:
                                logger.error(f"Background task '{name}' crashed: {exc}")
                        except asyncio.CancelledError:
                            logger.debug(f"Background task '{name}' was cancelled")
                            continue  # Don't restart cancelled tasks
                        except asyncio.InvalidStateError:
                            pass

                        # Restart the task
                        if name in self._task_factories:
                            logger.warning(f"Restarting background task '{name}'")
                            new_task = asyncio.create_task(
                                self._task_factories[name](),
                                name=name
                            )
                            self._tasks[name] = new_task
                        else:
                            logger.error(f"Cannot restart task '{name}' - no factory registered")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in task monitor: {e}")


async def retention_cleanup_loop(app: FastAPI):
    """Background task that runs retention cleanup hourly."""
    while True:
        try:
            # Sleep for 1 hour between cleanups
            await asyncio.sleep(RETENTION_CLEANUP_INTERVAL_SECONDS)

            # Run cleanup if we have config
            if hasattr(app.state, 'config') and app.state.config:
                retention_service = RetentionService(app.state.config)
                async with AsyncSessionLocal() as db:
                    await retention_service.cleanup_old_data(db)
        except asyncio.CancelledError:
            logger.debug("Retention cleanup task cancelled")
            raise  # Re-raise to properly signal cancellation
        except Exception as e:
            logger.error(f"Error in retention cleanup task: {e}")
            # Continue loop to retry on next interval


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context manager."""
    # Startup
    logger.info("Starting Speedarr...")
    setup_logger()

    # Validate secrets early
    validate_secrets()

    # Initialize database
    await init_db()
    logger.info("Database initialized")

    # Initialize config manager
    config_manager = ConfigManager(app)
    app.state.config_manager = config_manager

    # Load configuration from database
    async with AsyncSessionLocal() as db:
        config = await config_manager.load_config_from_db(db)

    if config:
        logger.info("Configuration loaded from database")

        # Initialize services
        decision_engine = DecisionEngine(config)
        controller_manager = ControllerManager(config)
        notification_service = NotificationService(config)

        # Test client connections
        logger.info("Testing download client connections...")
        connection_results = await controller_manager.test_connections()
        for client, conn_status in connection_results.items():
            if conn_status:
                logger.info(f"✓ {client} connected")
            else:
                logger.warning(f"✗ {client} connection failed")

        # Start polling monitor
        polling_monitor = PollingMonitor(
            config,
            decision_engine,
            controller_manager,
            AsyncSessionLocal,
            notification_service
        )
        await polling_monitor.start()

        # Store services in app state
        app.state.decision_engine = decision_engine
        app.state.controller_manager = controller_manager
        app.state.polling_monitor = polling_monitor
        app.state.notification_service = notification_service
        app.state.plex_client = polling_monitor.plex
        app.state.config = config
        app.state.setup_required = False

        # Initialize background task monitor
        task_monitor = BackgroundTaskMonitor(app)
        app.state.task_monitor = task_monitor

        # Register and start background tasks
        task_monitor.register_task(
            "retention_cleanup",
            lambda: retention_cleanup_loop(app)
        )
        logger.info("Retention cleanup task started (runs hourly)")

        # Start task monitor (checks every 60s)
        await task_monitor.start_monitoring(check_interval=TASK_MONITOR_CHECK_INTERVAL_SECONDS)
        logger.info("Background task monitor started")

        logger.info("Speedarr started successfully")
    else:
        # No configuration - setup mode
        logger.warning("No configuration found - running in setup mode")
        logger.info("Please complete setup via the web interface")
        app.state.setup_required = True
        app.state.config = None
        app.state.decision_engine = None
        app.state.controller_manager = None
        app.state.polling_monitor = None
        app.state.notification_service = None
        app.state.plex_client = None
        app.state.task_monitor = None

    yield

    # Shutdown
    logger.info("Shutting down Speedarr...")

    # Stop background task monitor (handles all registered tasks)
    if hasattr(app.state, 'task_monitor') and app.state.task_monitor:
        await app.state.task_monitor.stop()
        logger.debug("Background task monitor stopped")

    if hasattr(app.state, 'polling_monitor') and app.state.polling_monitor:
        await app.state.polling_monitor.stop()
    if hasattr(app.state, 'controller_manager') and app.state.controller_manager:
        # Timeout for restore_all_speeds to prevent hanging on unreachable clients
        try:
            await asyncio.wait_for(
                app.state.controller_manager.restore_all_speeds(),
                timeout=SHUTDOWN_RESTORE_TIMEOUT_SECONDS
            )
        except asyncio.TimeoutError:
            logger.warning("Timeout restoring speeds during shutdown - some clients may remain throttled")
        await app.state.controller_manager.close_all()
    if hasattr(app.state, 'notification_service') and app.state.notification_service:
        await app.state.notification_service.close()

    await close_db()
    logger.info("Speedarr shut down complete")


# Create FastAPI app
app = FastAPI(
    title="Speedarr",
    description="Intelligent bandwidth management for Plex and download clients",
    version="0.1.0",
    lifespan=lifespan
)

# Correlation ID middleware (first, to capture all requests)
app.add_middleware(CorrelationIdMiddleware)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    # Restrict to same-origin requests only (frontend served from same server)
    # This prevents malicious websites from making authenticated API requests
    allow_origins=[
        "http://localhost:9494",
        "http://127.0.0.1:9494",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router)
app.include_router(status.router)
app.include_router(control.router)
app.include_router(streams.router)
app.include_router(bandwidth.router)
app.include_router(settings_api.router)
app.include_router(decisions.router)


@app.get("/api/status/health")
async def health_check():
    """Combined health check endpoint (no auth required)."""
    return {
        "status": "healthy",
        "version": "0.1.0"
    }


@app.get("/api/status/live")
async def liveness_check():
    """
    Liveness probe - checks if the process is alive.
    Should return 200 if the app is running, regardless of dependencies.
    Used by Kubernetes/Docker to detect hung processes.
    """
    return {"status": "alive"}


@app.get("/api/status/ready")
async def readiness_check(request: Request):
    """
    Readiness probe - checks if the app is ready to serve requests.
    Checks database connectivity and core services.
    Used by load balancers to determine if traffic should be routed here.
    """
    checks = {
        "database": False,
        "config_loaded": False,
        "polling_monitor": False,
    }

    # Check database connectivity
    try:
        async with AsyncSessionLocal() as db:
            from sqlalchemy import text
            await db.execute(text("SELECT 1"))
            checks["database"] = True
    except Exception as e:
        logger.warning(f"Readiness check - database failed: {e}")

    # Check if config is loaded
    if hasattr(request.app.state, 'config') and request.app.state.config:
        checks["config_loaded"] = True

    # Check if polling monitor is running
    if hasattr(request.app.state, 'polling_monitor') and request.app.state.polling_monitor:
        polling_monitor = request.app.state.polling_monitor
        if polling_monitor._running:
            checks["polling_monitor"] = True

    # Determine overall status
    is_ready = all(checks.values())

    if is_ready:
        return {"status": "ready", "checks": checks}
    else:
        from fastapi import Response
        return Response(
            content='{"status": "not_ready", "checks": ' + str(checks).replace("'", '"').replace("True", "true").replace("False", "false") + '}',
            status_code=503,
            media_type="application/json"
        )


# Serve React frontend static files (if static directory exists)
static_dir = "static"
if os.path.exists(static_dir):
    # Serve static assets (JS, CSS, images)
    app.mount("/assets", StaticFiles(directory=os.path.join(static_dir, "assets")), name="assets")

    # Catch-all route for React Router - serves index.html for all non-API routes
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """Serve React SPA for all routes that don't match API endpoints."""
        # If the path is asking for a file that exists, serve it
        file_path = os.path.join(static_dir, full_path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        # Otherwise, serve index.html (for client-side routing)
        return FileResponse(os.path.join(static_dir, "index.html"))

    logger.info("Frontend static files served from /static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.host, port=settings.port)
