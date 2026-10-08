"""
Shadow Traffic — Risk Scorer & ETA Extrapolation Tests
Role in Architecture:
    Validates the 0–100 Congestion Risk Score, status classifications,
    weighted metric contributions, and ETA sanity capping.
"""

from datetime import datetime, timezone, timedelta
from shadow_shared.models import MetricEvent
from src.config import settings
from src.models import ForecastInterval, RiskStatus
from src.risk_scorer import RiskScorer


def test_weighting_scheme_justification():
    # Latency and Error Rate must dominate (35% each = 70% combined)
    assert settings.METRIC_WEIGHTS["avg_response_time_ms"] == 0.35
    assert settings.METRIC_WEIGHTS["error_rate_percent"] == 0.35
    assert settings.METRIC_WEIGHTS["request_rate"] == 0.20
    assert settings.METRIC_WEIGHTS["active_users"] == 0.10
    assert sum(settings.METRIC_WEIGHTS.values()) == 1.0


def test_high_rps_with_healthy_latency_stays_below_warning():
    """
    Validates that a spike in RPS alone (without latency or error degradation)
    does not trigger a critical alert.
    """
    scorer = RiskScorer()
    now = datetime(2026, 9, 21, 14, 0, 0, tzinfo=timezone.utc)

    # 3x RPS surge, but response time is 35ms and error rate is 0.05%
    metric = MetricEvent(
        site_id="site-scale-test",
        timestamp=now,
        active_users=1500,
        request_rate=1200.0,
        avg_response_time_ms=35.0,
        error_rate_percent=0.05,
    )

    baselines = {
        "active_users": (500.0, 50.0),
        "request_rate": (400.0, 40.0),
        "avg_response_time_ms": (35.0, 5.0),
        "error_rate_percent": (0.10, 0.05),
    }

    forecasts = {
        "request_rate": ForecastInterval(metric_name="request_rate", horizon_minutes=20, yhat=1250.0, yhat_lower=1100.0, yhat_upper=1400.0),
        "avg_response_time_ms": ForecastInterval(metric_name="avg_response_time_ms", horizon_minutes=20, yhat=36.0, yhat_lower=30.0, yhat_upper=40.0),
        "error_rate_percent": ForecastInterval(metric_name="error_rate_percent", horizon_minutes=20, yhat=0.05, yhat_lower=0.01, yhat_upper=0.10),
        "active_users": ForecastInterval(metric_name="active_users", horizon_minutes=20, yhat=1550.0, yhat_lower=1400.0, yhat_upper=1700.0),
    }

    score, status, eta, bottleneck, factors, rec = scorer.calculate_risk(
        current_metric=metric,
        baselines=baselines,
        forecasts=forecasts,
    )

    # Because latency and error rate (70% weight) are completely healthy,
    # status must not exceed Watch (40-59), and must NOT trigger Warning or Critical!
    assert status in [RiskStatus.NORMAL, RiskStatus.WATCH]
    assert score < 60.0
    assert bottleneck == "request_rate"


def test_eta_extrapolation_and_sanity_cap():
    scorer = RiskScorer()
    now = datetime(2026, 9, 21, 10, 0, 0, tzinfo=timezone.utc)

    # Current latency is 200ms, rising at 20ms/min towards 500ms threshold
    # Expected ETA: (500 - 200) / 20 = 15 minutes
    window = [
        MetricEvent(
            site_id="site-eta",
            timestamp=now - timedelta(minutes=10 - i),
            active_users=1000,
            request_rate=500.0,
            avg_response_time_ms=20.0 + (i * 20.0),
            error_rate_percent=0.2,
        )
        for i in range(10)
    ]
    curr = window[-1]

    eta = scorer._estimate_time_to_congestion(
        primary_bottleneck="avg_response_time_ms",
        current_metric=curr,
        recent_window=window,
    )
    assert eta is not None
    assert 13.0 <= eta <= 17.0

    # Flat trend test: slope ~ 0 -> ETA should be None (not 3 days)
    flat_window = [
        MetricEvent(
            site_id="site-flat",
            timestamp=now - timedelta(minutes=10 - i),
            active_users=500,
            request_rate=200.0,
            avg_response_time_ms=40.0 + (i * 0.01),
            error_rate_percent=0.1,
        )
        for i in range(10)
    ]
    flat_eta = scorer._estimate_time_to_congestion(
        primary_bottleneck="avg_response_time_ms",
        current_metric=flat_window[-1],
        recent_window=flat_window,
    )
    assert flat_eta is None
