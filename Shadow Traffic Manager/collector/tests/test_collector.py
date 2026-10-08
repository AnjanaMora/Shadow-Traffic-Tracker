"""
Shadow Traffic — Collector Agent Integration Tests
Role in Architecture:
    Validates end-to-end integration between CollectorAgent, the underlying
    TrafficSimulator, and ResilientMetricClient HTTP transmission.
"""

from unittest.mock import AsyncMock, patch
from shadow_shared.models import MetricEvent
from src.agent import TrafficSimulator, CollectorAgent


def test_simulator_generates_valid_metric_event():
    sim = TrafficSimulator(site_id="test-site")
    metric = sim.generate_metric()

    # Must be valid MetricEvent
    assert isinstance(metric, MetricEvent)
    assert metric.site_id == "test-site"
    assert metric.active_users >= 0
    assert metric.request_rate >= 0.0
    assert metric.avg_response_time_ms >= 0.0
    assert 0.0 <= metric.error_rate_percent <= 100.0


def test_simulator_spike_behavior():
    from datetime import datetime, timezone
    sim = TrafficSimulator(
        site_id="spike-site",
        base_users=2000,
        congestion_severity=4.0,
        start_time=datetime(2026, 9, 21, 14, 0, 0, tzinfo=timezone.utc),
    )
    sim.trigger_congestion_event(duration_seconds=60.0)
    for _ in range(10):
        metric = sim.generate_next_metric(step_seconds=3.0)

    assert metric.active_users > 1000
    assert metric.request_rate > 300


def test_collector_agent_send_success():
    import asyncio
    agent = CollectorAgent(backend_url="http://fake-backend:8000")
    metric = agent.simulator.generate_metric()

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value.status_code = 201
        success = asyncio.run(agent.send_metric(metric))
        assert success is True
        mock_post.assert_called_once()
