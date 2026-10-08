"""
Shadow Traffic — Resilient Client & Buffer Unit Tests
Role in Architecture:
    Validates network failure tolerance, local queue buffering (up to 100 events),
    exponential backoff computation, and automatic FIFO buffer drainage once
    backend connectivity is restored.
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
import httpx
from shadow_shared.models import MetricEvent
from src.client import ResilientMetricClient


def _create_sample_event(idx: int) -> MetricEvent:
    return MetricEvent(
        site_id=f"site-{idx}",
        timestamp=datetime.now(timezone.utc),
        active_users=100 + idx,
        request_rate=50.0 + idx,
        avg_response_time_ms=40.0,
        error_rate_percent=0.1,
    )


def test_exponential_backoff_calculation():
    client = ResilientMetricClient(
        initial_delay=1.0,
        max_delay=30.0,
        backoff_factor=2.0,
    )

    d0 = client.calculate_backoff(0)
    d1 = client.calculate_backoff(1)
    d2 = client.calculate_backoff(2)
    d3 = client.calculate_backoff(3)

    # Delay should increase exponentially
    assert 1.0 <= d0 <= 1.2
    assert 2.0 <= d1 <= 2.3
    assert 4.0 <= d2 <= 4.5
    assert 8.0 <= d3 <= 8.9

    # Max clamp check
    d_huge = client.calculate_backoff(10)
    assert d_huge <= 33.0  # Max delay 30 + 10% max jitter


def test_buffering_on_network_failure_and_fifo_order():
    async def _test():
        client = ResilientMetricClient(
            backend_url="http://fake-down-backend:8000",
            max_buffer_size=10,
        )

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = Exception("Connection Refused")

            # Push 5 events during network outage
            for i in range(5):
                success = await client.push(_create_sample_event(i))
                assert success is False

            # Buffer should now hold 5 events
            assert client.buffer_size == 5
            # First in buffer should be site-0 (FIFO)
            assert client.buffer[0].site_id == "site-0"
            assert client.buffer[-1].site_id == "site-4"

    asyncio.run(_test())


def test_buffer_overflow_cap_at_max_size():
    async def _test():
        client = ResilientMetricClient(
            backend_url="http://fake-down-backend:8000",
            max_buffer_size=100,  # Requirement: buffer up to 100 events
        )

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = Exception("Network Down")

            async with httpx.AsyncClient() as shared_http:
                # Enqueue 120 events (exceeding 100 limit)
                for i in range(120):
                    await client.push(_create_sample_event(i), client=shared_http)

            # Buffer size should cap strictly at 100
            assert client.buffer_size == 100
            assert client.total_dropped_overflow == 20
            # Oldest events 0-19 were dropped; head should now be site-20
            assert client.buffer[0].site_id == "site-20"
            assert client.buffer[-1].site_id == "site-119"

    asyncio.run(_test())


def test_buffer_flushes_when_backend_recovers():
    async def _test():
        client = ResilientMetricClient(
            backend_url="http://fake-backend:8000",
            max_buffer_size=100,
        )

        # 1. Pre-fill buffer with 3 events
        for i in range(3):
            client._enqueue(_create_sample_event(i))

        assert client.buffer_size == 3

        # 2. Mock recovery: HTTP 201 Created
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value.status_code = 201

            # Push a new event -> triggers flush of buffered items first
            new_event = _create_sample_event(99)
            success = await client.push(new_event)

            # Buffer should be completely emptied
            assert client.buffer_size == 0
            assert success is True
            # Called for 3 buffered + 1 new = 4 posts
            assert mock_post.call_count == 4

    asyncio.run(_test())
