"""
Simple in-memory rate limiter for protecting endpoints from brute force attacks.
"""
import asyncio
from datetime import datetime, timezone
from typing import Dict
from loguru import logger

from app.constants import (
    LOGIN_RATE_LIMIT_MAX_ATTEMPTS,
    LOGIN_RATE_LIMIT_WINDOW_SECONDS,
    LOGIN_RATE_LIMIT_BLOCK_SECONDS,
)


class RateLimiter:
    """
    Simple token bucket rate limiter.

    Tracks requests per IP address and blocks excessive requests.
    """

    def __init__(
        self,
        max_requests: int = 5,
        window_seconds: int = 60,
        block_seconds: int = 300
    ):
        """
        Initialize rate limiter.

        Args:
            max_requests: Maximum requests allowed in the window
            window_seconds: Time window in seconds
            block_seconds: How long to block after exceeding limit
        """
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.block_seconds = block_seconds
        self._requests: Dict[str, list] = {}  # IP -> list of timestamps
        self._blocked: Dict[str, datetime] = {}  # IP -> blocked until
        self._lock = asyncio.Lock()

    async def is_allowed(self, identifier: str) -> tuple[bool, int]:
        """
        Check if a request is allowed.

        Args:
            identifier: Usually IP address or user identifier

        Returns:
            Tuple of (is_allowed, seconds_until_unblocked)
        """
        async with self._lock:
            now = datetime.now(timezone.utc)

            # Check if blocked
            if identifier in self._blocked:
                blocked_until = self._blocked[identifier]
                if now < blocked_until:
                    remaining = int((blocked_until - now).total_seconds())
                    return (False, remaining)
                else:
                    del self._blocked[identifier]

            # Clean old requests
            cutoff = now.timestamp() - self.window_seconds
            if identifier in self._requests:
                self._requests[identifier] = [
                    ts for ts in self._requests[identifier]
                    if ts > cutoff
                ]
            else:
                self._requests[identifier] = []

            # Check rate
            if len(self._requests[identifier]) >= self.max_requests:
                # Block the IP
                blocked_until = now.replace(tzinfo=timezone.utc)
                from datetime import timedelta
                blocked_until = now + timedelta(seconds=self.block_seconds)
                self._blocked[identifier] = blocked_until
                logger.warning(f"Rate limit exceeded for {identifier}, blocked for {self.block_seconds}s")
                return (False, self.block_seconds)

            # Record request
            self._requests[identifier].append(now.timestamp())
            return (True, 0)

    async def clear(self, identifier: str):
        """Clear rate limit data for an identifier (e.g., on successful login)."""
        async with self._lock:
            self._requests.pop(identifier, None)
            self._blocked.pop(identifier, None)


# Global login rate limiter instance
login_rate_limiter = RateLimiter(
    max_requests=LOGIN_RATE_LIMIT_MAX_ATTEMPTS,
    window_seconds=LOGIN_RATE_LIMIT_WINDOW_SECONDS,
    block_seconds=LOGIN_RATE_LIMIT_BLOCK_SECONDS,
)
