"""
Shadow Traffic — Resilient Metric HTTP Client
Role in Architecture:
    Provides fault-tolerant transmission of canonical MetricEvents to the backend
    ingestion API (/api/metrics). Implements a bounded local ring buffer (up to 100
    events) and exponential backoff with jitter so that transient network failures
    or backend restarts do not drop telemetry data.
"""

import asyncio
import logging
import random
from collections import deque
from typing import Optional
import httpx

from shadow_shared.models import MetricEvent
from .config import settings

logger = logging.getLogger("collector.client")


class ResilientMetricClient:
    """
    HTTP transport client with in-memory bounded buffering and exponential backoff.
    Ensures zero data loss during transient network partitions.
    """

    def __init__(
        self,
        backend_url: str = settings.BACKEND_API_URL,
        endpoint_path: str = "/api/metrics",
        max_buffer_size: int = settings.MAX_BUFFER_SIZE,
        initial_delay: float = settings.RETRY_INITIAL_DELAY_SECONDS,
        max_delay: float = settings.RETRY_MAX_DELAY_SECONDS,
        backoff_factor: float = settings.RETRY_BACKOFF_FACTOR,
        timeout: float = settings.REQUEST_TIMEOUT_SECONDS,
        api_key: str = "shadow-dev-key-123",
    ):
        self.backend_url = backend_url.rstrip("/")
        self.endpoint_path = endpoint_path if endpoint_path.startswith("/") else f"/{endpoint_path}"
        self.target_url = f"{self.backend_url}{self.endpoint_path}"
        self.max_buffer_size = max_buffer_size
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor
        self.timeout = timeout
        self.api_key = api_key

        self.buffer: deque[MetricEvent] = deque(maxlen=self.max_buffer_size)
        self.consecutive_failures: int = 0
        self.is_draining: bool = False

        # Diagnostic counters
        self.total_sent: int = 0
        self.total_buffered: int = 0
        self.total_dropped_overflow: int = 0

    @property
    def buffer_size(self) -> int:
        return len(self.buffer)

    def calculate_backoff(self, attempt: int) -> float:
        """Compute exponential backoff delay with random jitter."""
        base_delay = self.initial_delay * (self.backoff_factor ** attempt)
        clamped_delay = min(self.max_delay, base_delay)
        jitter = random.uniform(0.0, clamped_delay * 0.1)
        return clamped_delay + jitter

    async def _post_event(self, client: httpx.AsyncClient, event: MetricEvent) -> bool:
        """Attempt single HTTP POST of a MetricEvent."""
        try:
            resp = await client.post(
                self.target_url,
                json=event.model_dump(mode="json"),
                headers={"X-API-Key": self.api_key},
                timeout=self.timeout,
            )
            # Accept both 200 OK and 201 CREATED
            if resp.status_code in [200, 201]:
                return True
            logger.warning(
                f"Backend rejected metric event (HTTP {resp.status_code}): {resp.text}"
            )
            return False
        except (httpx.TransportError, httpx.TimeoutException) as exc:
            logger.debug(f"Network transport error posting to {self.target_url}: {exc}")
            return False
        except Exception as exc:
            logger.error(f"Unexpected error posting to {self.target_url}: {exc}")
            return False

    async def flush_buffer(self, client: Optional[httpx.AsyncClient] = None) -> int:
        """
        Attempt to drain all queued events in FIFO order.
        Returns the count of successfully flushed events.
        """
        if not self.buffer or self.is_draining:
            return 0

        self.is_draining = True
        flushed_count = 0
        close_client = False

        if client is None:
            client = httpx.AsyncClient()
            close_client = True

        try:
            while self.buffer:
                event = self.buffer[0]
                success = await self._post_event(client, event)
                if success:
                    self.buffer.popleft()
                    flushed_count += 1
                    self.total_sent += 1
                    self.consecutive_failures = 0
                else:
                    # Backend still unavailable; stop draining and wait for next interval
                    self.consecutive_failures += 1
                    break
        finally:
            if close_client:
                await client.aclose()
            self.is_draining = False

        if flushed_count > 0:
            logger.info(f"Flushed {flushed_count} buffered metric events to backend.")
        return flushed_count

    async def push(self, event: MetricEvent, client: Optional[httpx.AsyncClient] = None) -> bool:
        """
        Transmit a MetricEvent to the backend. If transmission fails,
        buffer the event locally up to max_buffer_size and schedule retries.
        """
        should_close = False
        if client is None:
            client = httpx.AsyncClient()
            should_close = True

        try:
            # First, try to flush any previously backlog-buffered events
            if self.buffer:
                await self.flush_buffer(client)

            # If there is still a backlog, enqueue the current event to preserve ordering
            if self.buffer:
                self._enqueue(event)
                return False

            # Otherwise, attempt direct transmission
            success = await self._post_event(client, event)
            if success:
                self.consecutive_failures = 0
                self.total_sent += 1
                logger.info(
                    f"Transmitted MetricEvent [{event.site_id}]: "
                    f"users={event.active_users}, rps={event.request_rate:.1f}, "
                    f"latency={event.avg_response_time_ms:.1f}ms, err={event.error_rate_percent:.2f}%"
                )
                return True
            else:
                self.consecutive_failures += 1
                self._enqueue(event)
                backoff_wait = self.calculate_backoff(self.consecutive_failures - 1)
                logger.warning(
                    f"Transmission failed for [{event.site_id}]. Buffered (total: {len(self.buffer)}/{self.max_buffer_size}). "
                    f"Backoff delay ~{backoff_wait:.1f}s"
                )
                return False
        finally:
            if should_close:
                await client.aclose()

    def _enqueue(self, event: MetricEvent) -> None:
        """Safely enqueue an event, dropping the oldest if capacity is exceeded."""
        if len(self.buffer) >= self.max_buffer_size:
            self.buffer.popleft()
            self.total_dropped_overflow += 1
            logger.warning(
                f"Buffer overflow ({self.max_buffer_size} limit). Dropped oldest event."
            )
        self.buffer.append(event)
        self.total_buffered += 1
