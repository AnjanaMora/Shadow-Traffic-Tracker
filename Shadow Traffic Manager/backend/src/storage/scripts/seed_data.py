"""
Shadow Traffic — Historical Telemetry Seed Script
Role in Architecture:
    Populates TimescaleDB with realistic multi-week historical telemetry
    for local development and staging environments. Ensures the prediction
    engine has rich historical baselines (circadian diurnal curves, weekend
    variations, periodic traffic surges) to compute forecasts and identify anomalies.
"""

import argparse
import asyncio
import logging
import math
import random
from datetime import datetime, timezone, timedelta
from typing import List, Tuple
import asyncpg
from shadow_shared.models import MetricEvent
from ...config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("storage.seed")


def generate_historical_records(
    site_id: str = "shadow-ecommerce-prod",
    days: int = 14,
    interval_minutes: int = 2,
    end_time: datetime = None,
) -> List[Tuple]:
    """
    Generates realistic historical telemetry tuples suitable for bulk COPY.
    (site_id, timestamp, active_users, request_rate, avg_response_time_ms, error_rate_percent)
    """
    if end_time is None:
        end_time = datetime.now(timezone.utc)

    start_time = end_time - timedelta(days=days)
    current_time = start_time
    total_steps = int((days * 24 * 60) / interval_minutes)

    logger.info(
        f"Generating {total_steps} historical telemetry points for '{site_id}' "
        f"from {start_time.isoformat()} to {end_time.isoformat()} (interval: {interval_minutes}m)..."
    )

    records = []
    base_users = 1100

    while current_time <= end_time:
        hour = current_time.hour + (current_time.minute / 60.0)
        # 1. Diurnal cycle (peaks around 14:00, troughs around 03:00)
        angle = ((hour - 14.0) / 24.0) * 2.0 * math.pi
        diurnal = 0.35 + (((math.cos(angle) + 1.0) / 2.0) * 1.30)

        # 2. Weekend variation (Saturday=5, Sunday=6)
        weekend_factor = 0.82 if current_time.weekday() >= 5 else 1.0

        # 3. Gaussian noise
        noise = random.gauss(0, 45)

        # 4. Occasional historical promotional surges (e.g. 7 days ago around noon)
        surge_factor = 1.0
        days_ago = (end_time - current_time).total_seconds() / 86400.0
        if 6.8 <= days_ago <= 7.2 and 11.0 <= hour <= 15.0:
            surge_factor = 2.4

        raw_users = max(50, int((base_users * diurnal * weekend_factor * surge_factor) + noise))
        rps = round(max(2.0, (raw_users * 0.36) + random.uniform(-10, 10)), 2)

        # Latency degrades under surge
        if rps > 500.0:
            latency = round(45.0 + ((rps - 500.0) * 0.45) + random.uniform(5, 20), 2)
            error_rate = round(min(25.0, 0.2 + ((rps - 500.0) * 0.03) + random.uniform(0.1, 1.0)), 2)
        else:
            latency = round(max(20.0, 38.0 + (rps * 0.03) + random.uniform(-4, 6)), 2)
            error_rate = round(max(0.02, min(1.5, random.uniform(0.05, 0.3))), 2)

        records.append((
            site_id,
            current_time,
            raw_users,
            rps,
            latency,
            error_rate,
        ))

        current_time += timedelta(minutes=interval_minutes)

    return records


async def seed_timescaledb(
    database_url: str = settings.DATABASE_URL,
    site_id: str = "shadow-ecommerce-prod",
    days: int = 14,
    interval_minutes: int = 2,
    dry_run: bool = False,
) -> bool:
    """Bulk-inserts historical telemetry records into TimescaleDB."""
    records = generate_historical_records(
        site_id=site_id,
        days=days,
        interval_minutes=interval_minutes,
    )

    if dry_run:
        logger.info(f"[DRY-RUN] Generated {len(records)} records. Sample record: {records[0]}")
        return True

    clean_url = database_url.replace("postgresql+asyncpg://", "postgresql://")
    logger.info(f"Connecting to database at {clean_url}...")
    try:
        conn = await asyncpg.connect(clean_url)
    except Exception as exc:
        logger.error(f"Cannot connect to database to seed: {exc}")
        return False

    try:
        logger.info(f"Bulk loading {len(records)} records into 'metrics' table...")
        # Use copy_records_to_table for maximum insertion throughput
        await conn.copy_records_to_table(
            "metrics",
            records=records,
            columns=[
                "site_id",
                "timestamp",
                "active_users",
                "request_rate",
                "avg_response_time_ms",
                "error_rate_percent",
            ],
        )
        logger.info(f"Successfully loaded {len(records)} historical telemetry points.")
        return True
    except Exception as exc:
        logger.error(f"Error seeding database: {exc}", exc_info=True)
        return False
    finally:
        await conn.close()


def main():
    parser = argparse.ArgumentParser(description="Seed TimescaleDB with historical traffic data")
    parser.add_argument("--days", type=int, default=14, help="Number of historical days to seed (default: 14)")
    parser.add_argument("--site-id", type=str, default="shadow-ecommerce-prod", help="Site identifier")
    parser.add_argument("--interval-minutes", type=int, default=2, help="Sample interval in minutes (default: 2)")
    parser.add_argument("--database-url", type=str, default=settings.DATABASE_URL, help="Database connection URL")
    parser.add_argument("--dry-run", action="store_true", help="Generate records without inserting to DB")

    args = parser.parse_args()
    success = asyncio.run(
        seed_timescaledb(
            database_url=args.database_url,
            site_id=args.site_id,
            days=args.days,
            interval_minutes=args.interval_minutes,
            dry_run=args.dry_run,
        )
    )
    if not success:
        exit(1)


if __name__ == "__main__":
    main()
