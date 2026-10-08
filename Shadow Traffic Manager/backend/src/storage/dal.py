"""
Shadow Traffic — TimescaleDB Data Access Layer (DAL)
Role in Architecture:
    Provides high-throughput, asynchronous time-series data access using asyncpg.
    Implements idempotent metric ingestion, rolling window retrieval for the
    live dashboard, time-window queries for prediction baselines, and seasonal
    lookback queries (e.g., same time of day over the past N days/weeks).
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Union
import asyncpg

from shadow_shared.models import MetricEvent
from .models import MetricRollup

logger = logging.getLogger("backend.storage.dal")


class TimescaleDAL:
    """
    Data Access Layer for TimescaleDB using asyncpg connection pool.
    """

    def __init__(
        self,
        database_url: str,
        min_pool_size: int = 5,
        max_pool_size: int = 20,
    ):
        self.database_url = database_url
        self.min_pool_size = min_pool_size
        self.max_pool_size = max_pool_size
        self.pool: Optional[asyncpg.Pool] = None

        # In-memory buffer for offline test execution or initial connection fallback
        self._fallback_memory_store: List[MetricEvent] = []

    async def connect(self) -> bool:
        """Initialize the asyncpg connection pool."""
        try:
            # Strip '+asyncpg' prefix if present from SQLAlchemy-style connection URLs
            clean_url = self.database_url.replace("postgresql+asyncpg://", "postgresql://")
            self.pool = await asyncpg.create_pool(
                dsn=clean_url,
                min_size=self.min_pool_size,
                max_size=self.max_pool_size,
                command_timeout=10.0,
            )
            logger.info("TimescaleDB asyncpg connection pool established.")
            return True
        except Exception as exc:
            logger.warning(f"Could not connect to TimescaleDB pool ({exc}); using fallback store.")
            self.pool = None
            return False

    async def close(self) -> None:
        """Close the asyncpg connection pool."""
        if self.pool:
            await self.pool.close()
            self.pool = None

    async def insert_metric(self, event: MetricEvent) -> bool:
        """
        Idempotently insert a canonical MetricEvent into the 'metrics' hypertable.
        If an event with the same (site_id, timestamp) already exists, it updates the
        record to prevent duplicates and primary key collisions.
        """
        if self.pool:
            query = """
                INSERT INTO metrics (
                    site_id, timestamp, active_users, request_rate,
                    avg_response_time_ms, error_rate_percent
                )
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (site_id, timestamp)
                DO UPDATE SET
                    active_users = EXCLUDED.active_users,
                    request_rate = EXCLUDED.request_rate,
                    avg_response_time_ms = EXCLUDED.avg_response_time_ms,
                    error_rate_percent = EXCLUDED.error_rate_percent;
            """
            try:
                async with self.pool.acquire() as conn:
                    await conn.execute(
                        query,
                        event.site_id,
                        event.timestamp,
                        event.active_users,
                        event.request_rate,
                        event.avg_response_time_ms,
                        event.error_rate_percent,
                    )
                return True
            except Exception as exc:
                logger.error(f"Failed to insert metric into TimescaleDB: {exc}")
                return False

        # In-memory fallback
        # Maintain idempotency on (site_id, timestamp)
        for idx, existing in enumerate(self._fallback_memory_store):
            if existing.site_id == event.site_id and existing.timestamp == event.timestamp:
                self._fallback_memory_store[idx] = event
                return True

        self._fallback_memory_store.append(event)
        return True

    async def get_recent(self, site_id: str, minutes: int = 30) -> List[MetricEvent]:
        """
        Retrieve high-frequency raw telemetry points for a monitored site over
        the last N minutes (default: 30 minutes) to power live dashboard feeds.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)

        if self.pool:
            query = """
                SELECT site_id, timestamp, active_users, request_rate,
                       avg_response_time_ms, error_rate_percent
                FROM metrics
                WHERE site_id = $1 AND timestamp >= $2
                ORDER BY timestamp ASC;
            """
            try:
                async with self.pool.acquire() as conn:
                    rows = await conn.fetch(query, site_id, cutoff)
                    return [
                        MetricEvent(
                            site_id=r["site_id"],
                            timestamp=r["timestamp"],
                            active_users=r["active_users"],
                            request_rate=r["request_rate"],
                            avg_response_time_ms=r["avg_response_time_ms"],
                            error_rate_percent=r["error_rate_percent"],
                        )
                        for r in rows
                    ]
            except Exception as exc:
                logger.error(f"Failed to fetch recent metrics for {site_id}: {exc}")
                return []

        # In-memory fallback
        return [
            m for m in self._fallback_memory_store
            if m.site_id == site_id and m.timestamp >= cutoff
        ]

    async def get_historical_window(
        self, site_id: str, start: datetime, end: datetime
    ) -> List[MetricEvent]:
        """
        Retrieve metrics across an arbitrary historical time window [start, end].
        Used by the prediction engine to calculate trend slopes and baseline statistics.
        """
        if self.pool:
            query = """
                SELECT site_id, timestamp, active_users, request_rate,
                       avg_response_time_ms, error_rate_percent
                FROM metrics
                WHERE site_id = $1 AND timestamp >= $2 AND timestamp <= $3
                ORDER BY timestamp ASC;
            """
            try:
                async with self.pool.acquire() as conn:
                    rows = await conn.fetch(query, site_id, start, end)
                    return [
                        MetricEvent(
                            site_id=r["site_id"],
                            timestamp=r["timestamp"],
                            active_users=r["active_users"],
                            request_rate=r["request_rate"],
                            avg_response_time_ms=r["avg_response_time_ms"],
                            error_rate_percent=r["error_rate_percent"],
                        )
                        for r in rows
                    ]
            except Exception as exc:
                logger.error(f"Failed to fetch historical window: {exc}")
                return []

        # In-memory fallback
        return [
            m for m in self._fallback_memory_store
            if m.site_id == site_id and start <= m.timestamp <= end
        ]

    async def get_same_time_last_n_days(
        self,
        site_id: str,
        n: int = 14,
        target_time: Optional[datetime] = None,
        window_minutes: int = 30,
        same_weekday_only: bool = False,
    ) -> List[MetricEvent]:
        """
        Seasonal comparison query: extracts metrics around the same time of day
        (e.g., 10:00 AM +/- window_minutes/2) across the previous N days.

        If same_weekday_only=True, filters specifically to the same day of the week
        (e.g., "what did Tuesdays at 10:00 AM look like over the last N weeks").
        """
        anchor = target_time or datetime.now(timezone.utc)
        target_hour = anchor.hour
        target_minute = anchor.minute
        target_weekday = anchor.weekday()

        lookback_cutoff = anchor - timedelta(days=n)

        # Build window boundary in minutes from start of day
        anchor_min_of_day = target_hour * 60 + target_minute
        half_win = window_minutes // 2
        min_start = max(0, anchor_min_of_day - half_win)
        min_end = min(1439, anchor_min_of_day + half_win)

        if self.pool:
            # Query using time extraction on timestamp AT TIME ZONE 'UTC'
            if same_weekday_only:
                query = """
                    SELECT site_id, timestamp, active_users, request_rate,
                           avg_response_time_ms, error_rate_percent
                    FROM metrics
                    WHERE site_id = $1
                      AND timestamp >= $2
                      AND timestamp < $3
                      AND EXTRACT(DOW FROM timestamp AT TIME ZONE 'UTC') = $4
                      AND (EXTRACT(HOUR FROM timestamp AT TIME ZONE 'UTC') * 60 + EXTRACT(MINUTE FROM timestamp AT TIME ZONE 'UTC')) BETWEEN $5 AND $6
                    ORDER BY timestamp ASC;
                """
                # PostgreSQL EXTRACT(DOW): Sunday=0, Monday=1 .. Saturday=6
                # Python weekday(): Monday=0 .. Sunday=6
                pg_dow = (target_weekday + 1) % 7
                params = [site_id, lookback_cutoff, anchor, pg_dow, min_start, min_end]
            else:
                query = """
                    SELECT site_id, timestamp, active_users, request_rate,
                           avg_response_time_ms, error_rate_percent
                    FROM metrics
                    WHERE site_id = $1
                      AND timestamp >= $2
                      AND timestamp < $3
                      AND (EXTRACT(HOUR FROM timestamp AT TIME ZONE 'UTC') * 60 + EXTRACT(MINUTE FROM timestamp AT TIME ZONE 'UTC')) BETWEEN $4 AND $5
                    ORDER BY timestamp ASC;
                """
                params = [site_id, lookback_cutoff, anchor, min_start, min_end]

            try:
                async with self.pool.acquire() as conn:
                    rows = await conn.fetch(query, *params)
                    return [
                        MetricEvent(
                            site_id=r["site_id"],
                            timestamp=r["timestamp"],
                            active_users=r["active_users"],
                            request_rate=r["request_rate"],
                            avg_response_time_ms=r["avg_response_time_ms"],
                            error_rate_percent=r["error_rate_percent"],
                        )
                        for r in rows
                    ]
            except Exception as exc:
                logger.error(f"Failed to query same-time historical baseline: {exc}")
                return []

        # In-memory fallback
        results = []
        for m in self._fallback_memory_store:
            if m.site_id != site_id:
                continue
            if not (lookback_cutoff <= m.timestamp < anchor):
                continue
            if same_weekday_only and m.timestamp.weekday() != target_weekday:
                continue

            m_min_of_day = m.timestamp.hour * 60 + m.timestamp.minute
            if min_start <= m_min_of_day <= min_end:
                results.append(m)

        return sorted(results, key=lambda x: x.timestamp)

    async def get_rollups_1m(
        self, site_id: str, start: datetime, end: datetime
    ) -> List[MetricRollup]:
        """
        Query pre-aggregated 1-minute rollups from the continuous aggregate materialized view.
        """
        if not self.pool:
            return []

        query = """
            SELECT bucket, site_id, sample_count,
                   avg_active_users, max_active_users,
                   avg_request_rate, max_request_rate, p95_request_rate,
                   avg_response_time_ms, max_response_time_ms, p95_response_time_ms,
                   avg_error_rate_percent, max_error_rate_percent
            FROM metrics_1m_rollup
            WHERE site_id = $1 AND bucket >= $2 AND bucket <= $3
            ORDER BY bucket ASC;
        """
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(query, site_id, start, end)
                return [MetricRollup(**dict(r)) for r in rows]
        except Exception as exc:
            logger.warning(f"Continuous aggregate 1m query failed (view may not exist yet): {exc}")
            return []

    async def delete_metrics(self, site_id: str) -> bool:
        """
        Deletes all historical metrics for the given site_id from TimescaleDB and the fallback store.
        Used when a site is deleted with purge=true.
        """
        if self.pool:
            query = "DELETE FROM metrics WHERE site_id = $1;"
            try:
                async with self.pool.acquire() as conn:
                    res = await conn.execute(query, site_id)
                    logger.info(f"Purged metrics from TimescaleDB for site '{site_id}': {res}")
            except Exception as exc:
                logger.error(f"Failed to delete metrics from TimescaleDB for site '{site_id}': {exc}")

        # In-memory fallback
        before_count = len(self._fallback_memory_store)
        self._fallback_memory_store = [m for m in self._fallback_memory_store if m.site_id != site_id]
        deleted_count = before_count - len(self._fallback_memory_store)
        logger.info(f"Purged {deleted_count} in-memory metric events for site '{site_id}'")
        return True
