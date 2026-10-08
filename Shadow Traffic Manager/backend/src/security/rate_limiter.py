"""
Shadow Traffic — Per-Site Sliding-Window Rate Limiter
Role in Architecture:
    Protects the ingestion pipeline against flood attacks and runaway metric agents.
    Tracks ingestion request frequency per site_id within a 60-second sliding window,
    raising HTTP 429 Too Many Requests when limits are breached.
"""

import time
import logging
from collections import defaultdict, deque
from typing import Dict, Optional
from fastapi import HTTPException, status
from ..config import settings

logger = logging.getLogger("backend.security.ratelimit")


class SlidingWindowRateLimiter:
    """
    In-memory thread-safe sliding window rate limiter per site_id.
    """

    def __init__(self, max_requests: int = settings.RATE_LIMIT_REQUESTS_PER_MINUTE, window_seconds: float = 60.0):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        # site_id -> deque of timestamps
        self.request_timestamps: Dict[str, deque[float]] = defaultdict(deque)

    def check_rate_limit(self, site_id: str) -> None:
        """
        Records an access attempt for site_id.
        Raises HTTP 429 Too Many Requests if request count exceeds limit.
        """
        now = time.time()
        window_start = now - self.window_seconds
        queue = self.request_timestamps[site_id]

        # Purge entries outside sliding window
        while queue and queue[0] < window_start:
            queue.popleft()

        if len(queue) >= self.max_requests:
            retry_after = int(queue[0] + self.window_seconds - now) + 1
            logger.warning(
                f"Rate limit exceeded for site '{site_id}' ({len(queue)}/{self.max_requests} reqs/min)."
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded for site '{site_id}'. Max {self.max_requests} requests/minute allowed.",
                headers={"Retry-After": str(max(1, retry_after))},
            )

        queue.append(now)

    def reset(self, site_id: Optional[str] = None) -> None:
        """Reset rate limit counters (useful for testing)."""
        if site_id:
            self.request_timestamps.pop(site_id, None)
        else:
            self.request_timestamps.clear()


rate_limiter = SlidingWindowRateLimiter()
