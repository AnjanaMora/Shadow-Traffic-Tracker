"""
Shadow Traffic — Traffic Simulator Unit Tests
Role in Architecture:
    Validates synthetic traffic generation for the Collector service.
    Asserts seasonal day/night diurnal variations, weekend factors, random
    noise behavior, and multi-stage congestion event progression.
"""

from datetime import datetime, timezone
from shadow_shared.models import MetricEvent
from src.simulator import TrafficSimulator


def test_seasonal_diurnal_curve_day_vs_night():
    # 2:00 PM (14:00) peak vs 3:00 AM (03:00) lull
    peak_time = datetime(2026, 9, 21, 14, 0, 0, tzinfo=timezone.utc)
    night_time = datetime(2026, 9, 21, 3, 0, 0, tzinfo=timezone.utc)

    peak_factor = TrafficSimulator.calculate_diurnal_factor(peak_time)
    night_factor = TrafficSimulator.calculate_diurnal_factor(night_time)

    # Peak factor should be significantly greater than night factor
    assert peak_factor > 1.3
    assert night_factor < 0.6
    assert peak_factor > (night_factor * 2.0)


def test_weekday_vs_weekend_variation():
    # 2026-09-21 is Monday (weekday 0), 2026-09-26 is Saturday (weekday 5)
    monday = datetime(2026, 9, 21, 12, 0, 0, tzinfo=timezone.utc)
    saturday = datetime(2026, 9, 26, 12, 0, 0, tzinfo=timezone.utc)

    assert TrafficSimulator.calculate_weekend_factor(monday) == 1.0
    assert TrafficSimulator.calculate_weekend_factor(saturday) == 0.80


def test_simulator_generates_valid_schema_and_respects_noise():
    sim = TrafficSimulator(
        site_id="test-sim-site",
        base_users=1000,
        noise_percent=5.0,
        congestion_delay_seconds=9999.0,  # No congestion in this test
    )

    events = [sim.generate_next_metric(step_seconds=3.0) for _ in range(10)]

    for ev in events:
        assert isinstance(ev, MetricEvent)
        assert ev.site_id == "test-sim-site"
        assert ev.active_users > 0
        assert ev.request_rate > 0.0
        assert 10.0 <= ev.avg_response_time_ms <= 100.0  # Normal healthy latency
        assert 0.0 <= ev.error_rate_percent <= 2.0      # Normal baseline errors


def test_congestion_event_multi_stage_progression():
    """
    Validates that congestion ramps up progressively:
    Phase 1: Request rate escalates first.
    Phase 2: Response time / latency degrades as capacity saturates.
    Phase 3: Error rate spikes late in the congestion cycle.
    This enables the prediction engine to catch congestion early.
    """
    duration = 100.0  # 100 virtual seconds
    sim = TrafficSimulator(
        site_id="congestion-site",
        base_users=1000,
        noise_percent=0.0,  # Deterministic for exact progression check
        congestion_delay_seconds=10.0,
        congestion_duration_seconds=duration,
        congestion_severity=4.0,
        start_time=datetime(2026, 9, 21, 14, 0, 0, tzinfo=timezone.utc),
    )

    # 1. Baseline metric before congestion
    baseline = sim.generate_next_metric(step_seconds=5.0)
    assert not sim.is_congested
    assert baseline.error_rate_percent < 1.0
    assert baseline.avg_response_time_ms < 60.0

    # Fast forward to early congestion phase (~30% into congestion)
    # Elapsed ~ 40s (30s into congestion)
    early_phase = None
    for _ in range(7):
        early_phase = sim.generate_next_metric(step_seconds=5.0)

    assert sim.is_congested
    # Request rate and latency should have grown, but error rate should still be low
    assert early_phase.request_rate > baseline.request_rate * 1.35
    assert early_phase.avg_response_time_ms > baseline.avg_response_time_ms
    assert early_phase.error_rate_percent < 3.0  # Early warning window!

    # Fast forward to peak congestion phase (near 100s)
    peak_phase = None
    for _ in range(15):
        peak_phase = sim.generate_next_metric(step_seconds=5.0)

    # Peak phase: latency is severely degraded and error rate has spiked
    assert peak_phase.avg_response_time_ms > 200.0
    assert peak_phase.error_rate_percent > 5.0
