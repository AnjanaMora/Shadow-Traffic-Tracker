"""
Shadow Traffic — Database Migration Runner
Role in Architecture:
    Executes raw SQL migration scripts against PostgreSQL/TimescaleDB.
    Sets up the metrics hypertable, continuous aggregates, and retention policies.
"""

import asyncio
import logging
import os
from pathlib import Path
import asyncpg
from ...config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("storage.migrations")


async def run_migrations(database_url: str = settings.DATABASE_URL) -> bool:
    clean_url = database_url.replace("postgresql+asyncpg://", "postgresql://")
    migrations_dir = Path(__file__).parents[1] / "migrations"
    migration_files = sorted(migrations_dir.glob("*.sql"))

    if not migration_files:
        logger.warning("No migration SQL files found.")
        return True

    logger.info(f"Connecting to database to run migrations: {clean_url}")
    try:
        conn = await asyncpg.connect(clean_url)
    except Exception as exc:
        logger.error(f"Cannot connect to database: {exc}")
        return False

    try:
        for sql_path in migration_files:
            logger.info(f"Applying migration: {sql_path.name}")
            with open(sql_path, "r", encoding="utf-8") as f:
                sql_content = f.read()
            await conn.execute(sql_content)
            logger.info(f"Successfully applied {sql_path.name}")
        return True
    except Exception as exc:
        logger.error(f"Migration execution error: {exc}", exc_info=True)
        return False
    finally:
        await conn.close()


if __name__ == "__main__":
    success = asyncio.run(run_migrations())
    if not success:
        exit(1)
