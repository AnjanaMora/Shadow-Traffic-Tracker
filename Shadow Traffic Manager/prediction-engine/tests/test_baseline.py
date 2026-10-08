"""
Shadow Traffic — Seasonal Baseline Model Tests
Role in Architecture:
    Validates slot grouping by (day_of_week, hour_of_day), EWMA exponential
    decay, and cold start handling. Ensures Monday 9am != Sunday 3am.
"""

from datetime import datetime, timezone, timedelta
from shadow_shared.models import MetricEvent
from src.baseline import SeasonalBaselineModel


def test_time_slot_isolation_monday_9am_vs_sunday_3am():
    model = SeasonalBaselineModel()
    site = "site-slot-test"

    # Monday 9:00 AM (weekday 0, hour 9)
    mon_9am = datetime(2026, 9, 21, 9, 0, 0, tzinfo=timezone.utc)
    # Sunday 3:00 AM (weekday 6, hour 3)
    sun_3am = datetime(2026, 9, 20, 3, 0, 0, tzinfo=timezone.utc)

    # Train Monday 9am with heavy morning traffic
    for _ in range(5):
        model.update_single(
            MetricEvent(
                site_id=site,
                timestamp=mon_9am,
                active_users=3500,
                request_rate=1100.0,
                avg_response_time_ms=75.0,
                error_rate_percent=0.2,
            )
        )

    # Train Sunday 3am with quiet overnight traffic
    for _ in range(5):
        model.update_single(
            MetricEvent(
                site_id=site,
                timestamp=sun_3am,
                active_users=200,
                request_rate=50.0,
                avg_response_time_ms=32.0,
                error_rate_percent=0.02,
            )
        )

    # Verify that the model isolated the two slots
    mon_mean_rps, mon_std_rps = model.get_baseline(site, "request_rate", mon_9am)
    sun_mean_rps, sun_std_rps = model.get_baseline(site, "request_rate", sun_3am)

    assert mon_mean_rps > 1000.0
    assert sun_mean_rps < 100.0
    assert mon_mean_rps > (sun_mean_rps * 10.0)


def test_ewma_weights_recent_weeks_more_than_old_data():
    model = SeasonalBaselineModel(alpha=0.30)
    site = "site-ewma-test"
    ts = datetime(2026, 9, 21, 14, 0, 0, tzinfo=timezone.utc)

    # Old baseline: low traffic (100 RPS)
    for _ in range(10):
        model.update_single(
            MetricEvent(
                site_id=site,
                timestamp=ts,
                active_users=400,
                request_rate=100.0,
                avg_response_time_ms=35.0,
                error_rate_percent=0.1,
            )
        )

    old_mean, _ = model.get_baseline(site, "request_rate", ts)
    assert 95.0 <= old_mean <= 105.0

    # Recent observation shift: site doubled in size (250 RPS)
    for _ in range(3):
        model.update_single(
            MetricEvent(
                site_id=site,
                timestamp=ts,
                active_users=1000,
                request_rate=250.0,
                avg_response_time_ms=45.0,
                error_rate_percent=0.15,
            )
        )

    new_mean, _ = model.get_baseline(site, "request_rate", ts)
    # Mean should have shifted significantly towards recent 250 RPS
    assert new_mean > 160.0


def test_cold_start_minimum_std_floor():
    model = SeasonalBaselineModel()
    site = "unseen-site"
    ts = datetime(2026, 9, 21, 10, 0, 0, tzinfo=timezone.utc)

    # Never trained: should return valid diurnal estimates without error
    mean, std = model.get_baseline(site, "avg_response_time_ms", ts)
    assert mean > 0.0
    assert std >= model.min_std_floor
