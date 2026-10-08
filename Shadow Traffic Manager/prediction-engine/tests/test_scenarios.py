"""
Shadow Traffic — End-to-End Prediction Engine Scenario Tests
Role in Architecture:
    Validates end-to-end early warning capabilities across 3 core real-world scenarios:
    (a) Clearly normal traffic pattern scoring low (Normal status, score < 40).
    (b) Gradual congestion ramp-up triggering Warning before Critical.
    (c) Big but EXPECTED seasonal spike that is NOT flagged, proving seasonal awareness.
"""

from datetime import datetime, timezone, timedelta
from shadow_shared.models import MetricEvent
from src.models import RiskStatus
from src.service import assess_risk


def test_scenario_a_normal_traffic_scores_low():
    """
    Scenario (a): Normal daytime traffic operating well within seasonal expectations.
    Must score < 40 and classify as Normal.
    """
    site = "scenario-a-normal"
    anchor = datetime(2026, 9, 21, 14, 0, 0, tzinfo=timezone.utc)

    # 10 recent points of healthy telemetry
    window = [
        MetricEvent(
            site_id=site,
            timestamp=anchor - timedelta(minutes=10 - i),
            active_users=800 + (i * 5),
            request_rate=280.0 + (i * 2.0),
            avg_response_time_ms=42.0 + (i * 0.2),
            error_rate_percent=0.10,
        )
        for i in range(10)
    ]

    assessment = assess_risk(site_id=site, current_window=window)

    assert assessment.score < 40.0
    assert assessment.status == RiskStatus.NORMAL
    assert assessment.eta_minutes is None


def test_scenario_b_gradual_congestion_warning_before_critical():
    """
    Scenario (b): A gradual congestion ramp-up over 15 minutes.
    Validates that the engine issues a Warning (or Watch) early in the progression
    BEFORE hitting Critical saturation, proving true early-warning capability.
    """
    site = "scenario-b-ramp"
    anchor = datetime(2026, 9, 21, 10, 0, 0, tzinfo=timezone.utc)

    # Historical baseline training: normal load ~400 RPS, ~45ms latency, ~0.1% error
    history = [
        MetricEvent(
            site_id=site,
            timestamp=anchor - timedelta(days=7, minutes=i * 5),
            active_users=1000,
            request_rate=400.0,
            avg_response_time_ms=45.0,
            error_rate_percent=0.1,
        )
        for i in range(20)
    ]

    # Stage 1: Early ramp window (minute 0 to minute 8)
    # RPS +60%, Latency climbing to 180ms, but Error Rate STILL LOW at 0.4%
    early_window = [
        MetricEvent(
            site_id=site,
            timestamp=anchor + timedelta(minutes=i),
            active_users=1000 + (i * 120),
            request_rate=400.0 + (i * 50.0),        # 400 -> 800 RPS
            avg_response_time_ms=45.0 + (i * 16.0), # 45ms -> 173ms (climbing!)
            error_rate_percent=0.10 + (i * 0.04),   # Still low (~0.42%)
        )
        for i in range(9)
    ]

    early_assessment = assess_risk(
        site_id=site,
        current_window=early_window,
        historical_data=history,
    )

    # Must detect elevated risk (Watch or Warning) even while error rate is under 1%
    assert early_assessment.status in [RiskStatus.WATCH, RiskStatus.WARNING]
    assert early_assessment.score >= 40.0
    assert early_assessment.score < 80.0  # Not yet Critical!

    # Stage 2: Peak saturation (minute 15)
    # Severe latency surge (550ms) and 5xx errors (8.5%)
    critical_window = list(early_window) + [
        MetricEvent(
            site_id=site,
            timestamp=anchor + timedelta(minutes=9 + i),
            active_users=2000 + (i * 300),
            request_rate=850.0 + (i * 80.0),
            avg_response_time_ms=200.0 + (i * 60.0), # reaches 560ms
            error_rate_percent=1.0 + (i * 1.5),      # reaches 8.5%
        )
        for i in range(6)
    ]

    critical_assessment = assess_risk(
        site_id=site,
        current_window=critical_window,
        historical_data=history,
    )

    # Now in Critical status
    assert critical_assessment.status == RiskStatus.CRITICAL
    assert critical_assessment.score >= 80.0


def test_scenario_c_big_expected_spike_is_not_flagged():
    """
    Scenario (c): A big traffic spike (e.g. 2.5x traffic surge at Monday 14:00)
    that MATCHES the historical seasonal baseline for that exact time slot.
    Validates that the seasonal baseline model suppresses false alarms for
    predictable surges.
    """
    site = "scenario-c-seasonal"
    mon_2pm = datetime(2026, 9, 21, 14, 0, 0, tzinfo=timezone.utc)

    # Train baseline: historically, Monday 2:00 PM is peak sale hour
    # Expected traffic at this time is 1500 RPS, 4000 users, 65ms latency
    historical_data = []
    for week in [1, 2, 3]:
        prior_monday_2pm = mon_2pm - timedelta(days=7 * week)
        for minute in range(0, 60, 5):
            historical_data.append(
                MetricEvent(
                    site_id=site,
                    timestamp=prior_monday_2pm + timedelta(minutes=minute),
                    active_users=4000,
                    request_rate=1500.0,
                    avg_response_time_ms=65.0,
                    error_rate_percent=0.15,
                )
            )

    # Current event has the big 1500 RPS spike, but matches the Monday 2pm baseline!
    current_window = [
        MetricEvent(
            site_id=site,
            timestamp=mon_2pm - timedelta(minutes=10 - i),
            active_users=4100,
            request_rate=1520.0,           # Huge RPS, but expected!
            avg_response_time_ms=66.0,     # Normal expected latency
            error_rate_percent=0.15,       # Healthy errors
        )
        for i in range(10)
    ]

    assessment = assess_risk(
        site_id=site,
        current_window=current_window,
        historical_data=historical_data,
    )

    # Since the spike was expected for Monday 2pm, it must NOT be flagged as Warning or Critical
    assert assessment.status in [RiskStatus.NORMAL, RiskStatus.WATCH]
    assert assessment.score < 60.0
    assert "Critical" not in assessment.recommendation
