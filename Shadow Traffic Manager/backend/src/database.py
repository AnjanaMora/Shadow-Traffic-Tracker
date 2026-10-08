import logging
from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
from shadow_shared.models import MetricEvent, TrafficPrediction, AlertEvent
from .config import settings
from .storage.dal import TimescaleDAL

logger = logging.getLogger("backend.database")

engine = None
AsyncSessionLocal = None
dal = TimescaleDAL(database_url=settings.DATABASE_URL)


async def init_db() -> bool:
    """Initialize database tables, TimescaleDB hypertables, and DAL pool."""
    global engine, AsyncSessionLocal
    await dal.connect()
    try:
        engine = create_async_engine(
            settings.DATABASE_URL,
            echo=False,
            pool_pre_ping=True,
            pool_size=settings.DATABASE_POOL_SIZE,
            max_overflow=10,
        )
        AsyncSessionLocal = sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )

        async with engine.begin() as conn:
            # Enable TimescaleDB extension if available
            try:
                await conn.execute(text("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;"))
                logger.info("TimescaleDB extension enabled.")
            except Exception as e:
                logger.warning(f"Could not enable TimescaleDB extension (standard Postgres fallback): {e}")

            # Create metrics table
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS metrics (
                    id BIGSERIAL,
                    site_id VARCHAR(128) NOT NULL,
                    timestamp TIMESTAMPTZ NOT NULL,
                    active_users INTEGER NOT NULL,
                    request_rate DOUBLE PRECISION NOT NULL,
                    avg_response_time_ms DOUBLE PRECISION NOT NULL,
                    error_rate_percent DOUBLE PRECISION NOT NULL,
                    PRIMARY KEY (site_id, timestamp, id)
                );
            """))

            # Create hypertable on metrics
            try:
                await conn.execute(text("""
                    SELECT create_hypertable('metrics', 'timestamp', if_not_exists => TRUE);
                """))
                logger.info("Created or verified TimescaleDB hypertable for 'metrics'.")
            except Exception as e:
                logger.warning(f"Hypertable creation skipped or already exists: {e}")

            # Create predictions table
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS predictions (
                    id BIGSERIAL PRIMARY KEY,
                    site_id VARCHAR(128) NOT NULL,
                    predicted_at TIMESTAMPTZ NOT NULL,
                    horizon_seconds INTEGER NOT NULL,
                    predicted_request_rate DOUBLE PRECISION NOT NULL,
                    predicted_response_time_ms DOUBLE PRECISION NOT NULL,
                    congestion_risk_score DOUBLE PRECISION NOT NULL,
                    congestion_level VARCHAR(32) NOT NULL,
                    recommendation TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_predictions_site_time ON predictions (site_id, predicted_at DESC);
            """))

            # Create alerts table
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS alerts (
                    alert_id VARCHAR(64) PRIMARY KEY,
                    site_id VARCHAR(128) NOT NULL,
                    timestamp TIMESTAMPTZ NOT NULL,
                    level VARCHAR(32) NOT NULL,
                    title VARCHAR(256) NOT NULL,
                    message TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_alerts_site_time ON alerts (site_id, timestamp DESC);
            """))

        logger.info("Database schema initialized successfully.")
        return True
    except Exception as exc:
        logger.error(f"Database connection/initialization error: {exc}")
        engine = None
        AsyncSessionLocal = None
        return False


async def record_metric_event(event: MetricEvent) -> None:
    """Store metric event in TimescaleDB."""
    if not AsyncSessionLocal:
        return
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await session.execute(
                text("""
                    INSERT INTO metrics (site_id, timestamp, active_users, request_rate, avg_response_time_ms, error_rate_percent)
                    VALUES (:site_id, :timestamp, :active_users, :request_rate, :avg_response_time_ms, :error_rate_percent)
                """),
                {
                    "site_id": event.site_id,
                    "timestamp": event.timestamp,
                    "active_users": event.active_users,
                    "request_rate": event.request_rate,
                    "avg_response_time_ms": event.avg_response_time_ms,
                    "error_rate_percent": event.error_rate_percent,
                },
            )


async def get_recent_metrics(site_id: Optional[str] = None, limit: int = 50) -> List[MetricEvent]:
    """Retrieve recent metrics."""
    if not AsyncSessionLocal:
        return []
    async with AsyncSessionLocal() as session:
        if site_id:
            query = text("""
                SELECT site_id, timestamp, active_users, request_rate, avg_response_time_ms, error_rate_percent
                FROM metrics
                WHERE site_id = :site_id
                ORDER BY timestamp DESC
                LIMIT :limit
            """)
            result = await session.execute(query, {"site_id": site_id, "limit": limit})
        else:
            query = text("""
                SELECT site_id, timestamp, active_users, request_rate, avg_response_time_ms, error_rate_percent
                FROM metrics
                ORDER BY timestamp DESC
                LIMIT :limit
            """)
            result = await session.execute(query, {"limit": limit})

        rows = result.mappings().all()
        return [
            MetricEvent(
                site_id=row["site_id"],
                timestamp=row["timestamp"],
                active_users=row["active_users"],
                request_rate=row["request_rate"],
                avg_response_time_ms=row["avg_response_time_ms"],
                error_rate_percent=row["error_rate_percent"],
            )
            for row in reversed(rows)
        ]


async def record_prediction(pred: TrafficPrediction) -> None:
    """Save prediction forecast to database."""
    if not AsyncSessionLocal:
        return
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await session.execute(
                text("""
                    INSERT INTO predictions (site_id, predicted_at, horizon_seconds, predicted_request_rate,
                                             predicted_response_time_ms, congestion_risk_score, congestion_level, recommendation)
                    VALUES (:site_id, :predicted_at, :horizon_seconds, :predicted_request_rate,
                            :predicted_response_time_ms, :congestion_risk_score, :congestion_level, :recommendation)
                """),
                {
                    "site_id": pred.site_id,
                    "predicted_at": pred.predicted_at,
                    "horizon_seconds": pred.horizon_seconds,
                    "predicted_request_rate": pred.predicted_request_rate,
                    "predicted_response_time_ms": pred.predicted_response_time_ms,
                    "congestion_risk_score": pred.congestion_risk_score,
                    "congestion_level": pred.congestion_level.value,
                    "recommendation": pred.recommendation,
                },
            )


async def record_alert(alert: AlertEvent) -> None:
    """Save triggered alert to database."""
    if not AsyncSessionLocal:
        return
    try:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                await session.execute(
                    text("""
                        INSERT INTO alerts (alert_id, site_id, timestamp, level, title, message)
                        VALUES (:alert_id, :site_id, :timestamp, :level, :title, :message)
                        ON CONFLICT (alert_id) DO NOTHING
                    """),
                    {
                        "alert_id": alert.alert_id,
                        "site_id": alert.site_id,
                        "timestamp": alert.timestamp,
                        "level": alert.level.value,
                        "title": alert.title,
                        "message": alert.message,
                    },
                )
    except Exception as exc:
        logger.debug(f"Could not persist alert to database (offline/unreachable): {exc}")


async def clear_alerts_db(site_id: Optional[str] = None, alert_id: Optional[str] = None) -> None:
    """Clear alerts from database audit table."""
    if not AsyncSessionLocal:
        return
    try:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                if alert_id:
                    await session.execute(text("DELETE FROM alerts WHERE alert_id = :alert_id"), {"alert_id": alert_id})
                elif site_id:
                    await session.execute(text("DELETE FROM alerts WHERE site_id = :site_id"), {"site_id": site_id})
                else:
                    await session.execute(text("DELETE FROM alerts"))
    except Exception as exc:
        logger.debug(f"Could not clear alerts from database: {exc}")


async def check_db_health() -> bool:
    """Quick DB ping for /health check with short timeout."""
    if not AsyncSessionLocal:
        return False
    try:
        import asyncio
        async def _ping():
            async with AsyncSessionLocal() as session:
                await session.execute(text("SELECT 1"))
        await asyncio.wait_for(_ping(), timeout=1.0)
        return True
    except Exception:
        return False
