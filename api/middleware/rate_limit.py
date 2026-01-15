"""
MSI Automotive - Rate Limiting Middleware.

Simple in-memory rate limiter for API endpoints.
For production with multiple instances, consider Redis-based rate limiting.
"""

import logging
import time
from collections import defaultdict

logger = logging.getLogger(__name__)


class InMemoryRateLimiter:
    """
    In-memory rate limiter using sliding window.

    NOTE: This is suitable for single-instance deployments.
    For multi-instance production, use Redis-based rate limiting.
    """

    def __init__(self):
        self._requests: dict[str, list[float]] = defaultdict(list)

    def check_rate_limit(
        self,
        key: str,
        max_requests: int,
        window_seconds: int,
    ) -> bool:
        """
        Check if request is within rate limit.

        Args:
            key: Unique identifier (e.g., "upload:username" or "ip:1.2.3.4")
            max_requests: Maximum allowed requests in window
            window_seconds: Time window in seconds

        Returns:
            True if request is allowed, False if rate limited
        """
        now = time.time()
        window_start = now - window_seconds

        # Remove requests outside the window
        self._requests[key] = [
            req_time
            for req_time in self._requests[key]
            if req_time > window_start
        ]

        # Check if under limit
        if len(self._requests[key]) >= max_requests:
            logger.warning(
                f"Rate limit exceeded for {key}: "
                f"{len(self._requests[key])}/{max_requests} in {window_seconds}s"
            )
            return False

        # Record this request
        self._requests[key].append(now)
        return True

    def get_remaining(
        self,
        key: str,
        max_requests: int,
        window_seconds: int,
    ) -> int:
        """
        Get remaining requests in the current window.

        Args:
            key: Unique identifier
            max_requests: Maximum allowed requests in window
            window_seconds: Time window in seconds

        Returns:
            Number of remaining requests allowed
        """
        now = time.time()
        window_start = now - window_seconds

        # Count requests in current window
        current_requests = sum(
            1 for req_time in self._requests.get(key, [])
            if req_time > window_start
        )

        return max(0, max_requests - current_requests)

    def reset(self, key: str) -> None:
        """Reset rate limit for a specific key."""
        if key in self._requests:
            del self._requests[key]

    def clear_all(self) -> None:
        """Clear all rate limit data."""
        self._requests.clear()


# Singleton instance
_rate_limiter: InMemoryRateLimiter | None = None


def get_rate_limiter() -> InMemoryRateLimiter:
    """Get singleton rate limiter instance."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = InMemoryRateLimiter()
    return _rate_limiter
