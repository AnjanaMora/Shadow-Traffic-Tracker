"""
Shadow Traffic — Storage Layer & TimescaleDAL Unit Tests
Role in Architecture:
    Tests the TimescaleDB Data Access Layer (DAL), query logic, idempotency,
    seasonal lookback extraction, and seed generation algorithms.
"""

import asyncio
import pytest
from datetime import datetime, timezone, timedelta
from shadow_shared.models import MetricEvent
from src.storage.dal import TimescaleDAL
from src.storage.models import MetricRollup
from src.storage.scripts.seed_data import generate_historical_records


def _make_metric(site_id: str, ts: datetime, rps: float = 100.0, users: int = 500) -> MetricEvent:
    return MetricEvent(
        site_id=site_id,
        timestamp=ts,
        active_users=users,
        request_rate=rps,
        avg_response_time_ms=45.0,
        error_rate_percent=0.2,
    )


def test_dal_insert_idempotency_duplicate_timestamp():
    async def _test():
        dal = TimescaleDAL(database_url="postgresql://fake-db:5432/test")
        ts = datetime.now(timezone.utc) - timedelta(minutes=5)

        # 1. Initial insert
        event1 = _make_metric("site-a", ts, rps=100.0, users=300)
        success1 = await dal.insert_metric(event1)
        assert success1 is True

        # 2. Duplicate insert with updated metrics
        event2 = _make_metric("site-a", ts, rps=250.0, users=800)
        success2 = await dal.insert_metric(event2)
        assert success2 is True

        # In fallback store, there should be exactly 1 item and it should be updated
        recent = await dal.get_recent("site-a", minutes=60)
        matching = [m for m in recent if m.timestamp == ts]
        assert len(matching) == 1
        assert matching[0].request_rate == 250.0
        assert matching[0].active_users == 800

    asyncio.run(_test())


def test_dal_get_recent_time_window_and_site_isolation():
    async def _test():
        dal = TimescaleDAL(database_url="postgresql://fake-db:5432/test")
        now = datetime.now(timezone.utc)

        # Insert events at various offsets
        event_fresh = _make_metric("site-recent", now - timedelta(minutes=10))
        event_stale = _make_metric("site-recent", now - timedelta(minutes=45))  # > 30m old
        event_other = _make_metric("site-other", now - timedelta(minutes=5))

        await dal.insert_metric(event_fresh)
        await dal.insert_metric(event_stale)
        await dal.insert_metric(event_other)

        recent = await dal.get_recent("site-recent", minutes=30)
        assert len(recent) == 1
        assert recent[0].timestamp == event_fresh.timestamp
        assert recent[0].site_id == "site-recent"

    asyncio.run(_test())


def test_dal_get_historical_window():
    async def _test():
        dal = TimescaleDAL(database_url="postgresql://fake-db:5432/test")
        base = datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc)

        # Add 5 events separated by 1 hour
        for i in range(5):
            await dal.insert_metric(_make_metric("site-hist", base + timedelta(hours=i)))

        # Query window for hours 1 to 3 inclusive
        start = base + timedelta(hours=1)
        end = base + timedelta(hours=3)

        results = await dal.get_historical_window("site-hist", start=start, end=end)
        assert len(results) == 3
        assert results[0].timestamp == start
        assert results[-1].timestamp == end

    asyncio.run(_test())


def test_dal_get_same_time_last_n_days_seasonal_query():
    async def _test():
        dal = TimescaleDAL(database_url="postgresql://fake-db:5432/test")

        # Anchor at Tuesday 10:00 AM UTC
        anchor = datetime(2026, 9, 22, 10, 0, 0, tzinfo=timezone.utc)  # Tuesday

        # Populate 14 days of data with sample points at 10:00 AM and 03:00 AM
        for day in range(1, 15):
            day_date = anchor - timedelta(days=day)
            # 10:00 AM target time
            await dal.insert_metric(_make_metric("site-seasonal", day_date.replace(hour=10, minute=0, second=0)))
            # 03:00 AM non-target time (should be filtered out by time-of-day filter)
            await dal.insert_metric(_make_metric("site-seasonal", day_date.replace(hour=3, minute=0, second=0)))

        # Query same time over last 14 days (all days)
        same_time_events = await dal.get_same_time_last_n_days(
            site_id="site-seasonal",
            n=14,
            target_time=anchor,
            window_minutes=30,
            same_weekday_only=False,
        )
        assert len(same_time_events) == 14
        for ev in same_time_events:
            assert ev.timestamp.hour == 10

        # Query only same weekday (Tuesdays only)
        tuesdays_only = await dal.get_same_time_last_n_days(
            site_id="site-seasonal",
            n=14,
            target_time=anchor,
            window_minutes=30,
            same_weekday_only=True,
        )
        # Over 14 days, exactly 2 prior Tuesdays exist (7 days ago and 14 days ago)
        assert len(tuesdays_only) == 2
        for ev in tuesdays_only:
            assert ev.timestamp.weekday() == anchor.weekday()
            assert ev.timestamp.hour == 10

    asyncio.run(_test())


def test_seed_generator_produces_realistic_multi_day_dataset():
    records = generate_historical_records(
        site_id="test-seed",
        days=3,
        interval_minutes=5,
        end_time=datetime(2026, 9, 21, 12, 0, 0, tzinfo=timezone.utc),
    )

    # 3 days * 24h * 12 points/h = 864 (+1 for inclusive end)
    assert len(records) >= 864
    first = records[0]
    last = records[-1]

    assert first[0] == "test-seed"
    assert first[2] > 0      # active users
    assert first[3] > 0.0    # rps
    assert first[4] > 0.0    # latency
    assert 0.0 <= first[5] <= 100.0  # error rate


def test_metric_rollup_model_validation():
    rollup = MetricRollup(
        bucket=datetime(2026, 9, 21, 10, 0, 0, tzinfo=timezone.utc),
        site_id="site-rollup",
        sample_count=20,
        avg_active_users=1200,
        max_active_users=1500,
        avg_request_rate=450.2,
        max_request_rate=580.0,
        p95_request_rate=540.0,
        avg_response_time_ms=52.5,
        max_response_time_ms=120.0,
        p95_response_time_ms=88.0,
        avg_error_rate_percent=0.15,
        max_error_rate_percent=1.2,
    )
    assert rollup.site_id == "site-rollup"
    assert rollup.sample_count == 20
    assert rollup.p95_request_rate == 540.0
