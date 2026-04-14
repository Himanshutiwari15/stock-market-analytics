"""
src/pipeline/load.py — Load step of the ETL pipeline
=====================================================
The Load step takes validated StockPrice ORM objects from the
transform step and persists them to the PostgreSQL database.

KEY DESIGN: Idempotent inserts
  The pipeline runs every 60 seconds. If it runs twice in quick
  succession (restart, bug, manual trigger), the same data would
  be fetched twice. We must NOT create duplicate rows.

  Solution: INSERT ... ON CONFLICT DO NOTHING
  If a row with the same (symbol, fetched_at) already exists,
  the database silently skips it. No error, no duplicate.
  This property — safe to run multiple times with the same result —
  is called IDEMPOTENCY. It is a fundamental requirement of any
  production data pipeline.

  Without idempotency, a single pipeline restart would double your
  data. After a week of daily restarts, your database is chaos.

HOW we count inserted vs skipped:
  PostgreSQL's rowcount tells us how many rows were actually inserted
  (0 if skipped by ON CONFLICT). We track both so the scheduler can
  log meaningful pipeline health information.
"""

import logging
from typing import NamedTuple

from sqlalchemy.dialects.postgresql import insert as pg_insert

from src.database.connection import get_session
from src.database.models import StockPrice

logger = logging.getLogger(__name__)


class LoadResult(NamedTuple):
    """
    Result of a load operation.

    Using NamedTuple instead of a plain tuple means callers can write:
        result.inserted  instead of  result[0]
    Much more readable in logs and tests.
    """
    inserted: int   # rows newly written to the database
    skipped: int    # rows that already existed (ON CONFLICT DO NOTHING)
    failed: int     # rows that failed due to unexpected errors


def load(records: list[StockPrice]) -> LoadResult:
    """
    Insert StockPrice records into PostgreSQL.

    Uses INSERT ... ON CONFLICT DO NOTHING so duplicate records
    (same symbol + fetched_at) are silently skipped, not rejected.

    Args:
        records: List of validated StockPrice objects from transform().

    Returns:
        LoadResult(inserted, skipped, failed) — counts for each outcome.
    """
    if not records:
        logger.warning("LOAD: No records to insert.")
        return LoadResult(inserted=0, skipped=0, failed=0)

    logger.info(f"LOAD: Inserting {len(records)} record(s)...")

    inserted = 0
    skipped = 0
    failed = 0

    with get_session() as session:
        for record in records:
            try:
                # pg_insert is PostgreSQL-specific and supports ON CONFLICT.
                # We build a VALUES dict from the ORM object's attributes.
                stmt = pg_insert(StockPrice).values(
                    symbol=record.symbol,
                    price=record.price,
                    volume=record.volume,
                    fetched_at=record.fetched_at,
                ).on_conflict_do_nothing(
                    # These two columns form the unique constraint.
                    # If a row with this (symbol, fetched_at) pair already
                    # exists, skip this insert silently.
                    index_elements=["symbol", "fetched_at"]
                )

                result = session.execute(stmt)

                # rowcount = 1 means a row was inserted.
                # rowcount = 0 means it was skipped (conflict).
                if result.rowcount and result.rowcount > 0:
                    inserted += 1
                    logger.debug(
                        f"  Inserted: {record.symbol} @ ${float(record.price):.2f}"
                    )
                else:
                    skipped += 1
                    logger.debug(
                        f"  Skipped (duplicate): {record.symbol} @ {record.fetched_at}"
                    )

            except Exception as e:
                # A single record failure should not abort the entire batch.
                # Log it and continue with the next record.
                failed += 1
                logger.error(
                    f"  FAILED to insert {record.symbol}: {type(e).__name__}: {e}"
                )

    load_result = LoadResult(inserted=inserted, skipped=skipped, failed=failed)
    logger.info(
        f"LOAD: Complete — "
        f"inserted={inserted}, skipped={skipped}, failed={failed}"
    )
    return load_result
