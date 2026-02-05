"""
Correlation ID middleware for request tracing.
"""
import uuid
from contextvars import ContextVar
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from loguru import logger

# Context variable to store correlation ID for the current request
correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="")


def get_correlation_id() -> str:
    """Get the correlation ID for the current request context."""
    return correlation_id_var.get()


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """
    Middleware that adds a correlation ID to each request.

    The correlation ID is:
    1. Read from X-Correlation-ID header if present (for distributed tracing)
    2. Generated as a new UUID if not present
    3. Stored in context for access in logs
    4. Added to response headers
    """

    HEADER_NAME = "X-Correlation-ID"

    async def dispatch(self, request: Request, call_next):
        # Get or generate correlation ID
        correlation_id = request.headers.get(self.HEADER_NAME)
        if not correlation_id:
            correlation_id = str(uuid.uuid4())[:8]  # Short 8-char ID for readability

        # Store in context variable for logging
        token = correlation_id_var.set(correlation_id)

        try:
            # Process request
            response = await call_next(request)

            # Add correlation ID to response headers
            response.headers[self.HEADER_NAME] = correlation_id

            return response
        finally:
            # Reset context variable
            correlation_id_var.reset(token)


def correlation_id_filter(record):
    """
    Loguru filter that adds correlation_id to log records.
    """
    record["extra"]["correlation_id"] = get_correlation_id() or "-"
    return True
