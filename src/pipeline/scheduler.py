"""
src/pipeline/scheduler.py — Pipeline orchestrator and scheduler
===============================================================
This module ties the three ETL steps together into a single pipeline
and runs it on a configurable schedule using APScheduler.

PIPELINE FLOW:
  run_once()
    │
    ├─ 1. extract()   → raw_records: list[dict]
    │
    ├─ 2. transform() → clean_records: list[StockPrice]
    │
    └─ 3. load()      → LoadResult(inserted, skipped, failed)

SCHEDULER:
  APScheduler runs run_once() every FETCH_INTERVAL_SECONDS seconds.
  It runs in the same process as your Python app (no separate process).

  WHY APScheduler over cron?
    - cron is an OS-level scheduler — adding a job requires editing
      system files (crontab) and knowing the server setup.
    - APScheduler is a Python library — the schedule is defined in
      code, version-controlled, and works the same on every machine.
    - For a single-machine pipeline, APScheduler is the right tool.
    - At scale (distributed, fault-tolerant), you'd graduate to
      Apache Airflow, Prefect, or Dagster. APScheduler is the
      educational stepping stone to those platforms.

  WHY next_run_time=now?
    By default, APScheduler waits one full interval before the first
    run. Setting next_run_time to now means the pipeline runs
    immediately on startup, then again after each interval.
    This is almost always the desired behaviour.
"""

import logging
import signal
import sys
from datetime import datetime, timezone

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger

from src.config import FETCH_INTERVAL_SECONDS
from src.database.connection import check_connection
from src.monitoring.metrics import (
    PIPELINE_LAST_DURATION,
    PIPELINE_LAST_INSERTED,
    PIPELINE_RECORDS_INSERTED,
    PIPELINE_RECORDS_SKIPPED,
    PIPELINE_RUNS,
    PIPELINE_UP,
    start_metrics_server,
)
from src.pipeline.extract import extract
from src.pipeline.load import LoadResult, load
from src.pipeline.transform import transform

logger = logging.getLogger(__name__)


def run_once() -> dict:
    """
    Execute one complete ETL cycle: Extract → Transform → Load.

    This function is the unit of work scheduled by APScheduler.
    It is also called directly for one-off runs and testing.

    Returns:
        A summary dict with counts for each pipeline stage.
        Useful for logging, monitoring, and assertions in tests.
    """
    run_start = datetime.now(timezone.utc)
    logger.info("=" * 55)
    logger.info("PIPELINE RUN STARTED")
    logger.info("=" * 55)

    try:
        # --- Step 1: Extract ---
        raw_records = extract()

        # --- Step 2: Transform ---
        clean_records = transform(raw_records)

        # --- Step 3: Load ---
        result: LoadResult = load(clean_records)

        # --- Summary ---
        duration_ms = (datetime.now(timezone.utc) - run_start).total_seconds() * 1000

        summary = {
            "timestamp": run_start.isoformat(),
            "extracted": len(raw_records),
            "transformed": len(clean_records),
            "inserted": result.inserted,
            "skipped": result.skipped,
            "failed": result.failed,
            "duration_ms": round(duration_ms, 1),
        }

        logger.info(
            f"PIPELINE COMPLETE | "
            f"extracted={summary['extracted']} | "
            f"transformed={summary['transformed']} | "
            f"inserted={summary['inserted']} | "
            f"skipped={summary['skipped']} | "
            f"failed={summary['failed']} | "
            f"duration={summary['duration_ms']}ms"
        )
        logger.info("=" * 55)

        # --- Record Prometheus metrics ---
        # These numbers are now queryable in Grafana via PromQL.
        PIPELINE_RUNS.labels(status="success").inc()
        PIPELINE_RECORDS_INSERTED.inc(result.inserted)
        PIPELINE_RECORDS_SKIPPED.inc(result.skipped)
        PIPELINE_LAST_DURATION.set(duration_ms / 1000)   # store as seconds
        PIPELINE_LAST_INSERTED.set(result.inserted)
        PIPELINE_UP.set(1)  # pipeline completed successfully

        return summary

    except Exception as exc:
        # If any ETL step raises an exception, record the failure and re-raise.
        # The scheduler will log the traceback; we just update the health metrics.
        duration_ms = (datetime.now(timezone.utc) - run_start).total_seconds() * 1000
        PIPELINE_RUNS.labels(status="failed").inc()
        PIPELINE_UP.set(0)  # signal to Grafana that something is wrong
        logger.error(
            f"Pipeline run FAILED after {duration_ms:.0f}ms: {exc}",
            exc_info=True,
        )
        raise


def start() -> None:
    """
    Start the pipeline scheduler.

    Runs run_once() immediately, then repeats every FETCH_INTERVAL_SECONDS.
    Blocks the main thread (use as the main entry point of the app).
    Handles Ctrl+C and SIGTERM gracefully for clean Docker shutdowns.
    """
    logger.info("Initialising Stock Market Analytics Pipeline...")
    logger.info(f"Fetch interval: every {FETCH_INTERVAL_SECONDS} seconds")

    # Check the database is reachable before starting.
    # There is no point scheduling the pipeline if the DB is down.
    logger.info("Checking database connection...")
    if not check_connection():
        logger.error(
            "Cannot connect to the database. "
            "Make sure PostgreSQL is running (docker compose up postgres -d) "
            "and POSTGRES_PASSWORD is set in your .env file."
        )
        sys.exit(1)
    logger.info("Database connection: OK")

    # Start the Prometheus metrics HTTP server.
    # This runs in a background thread — it does NOT block the scheduler.
    # Prometheus will scrape http://app:8000/metrics every 15 seconds.
    start_metrics_server(port=8000)

    # Set pipeline_up = 1 immediately so Grafana shows "RUNNING" from the
    # first Prometheus scrape, even before the first ETL run completes.
    PIPELINE_UP.set(1)

    # Create the scheduler.
    # timezone="UTC": all job times are expressed in UTC internally.
    scheduler = BlockingScheduler(timezone="UTC")

    scheduler.add_job(
        func=run_once,
        trigger=IntervalTrigger(seconds=FETCH_INTERVAL_SECONDS),
        id="etl_pipeline",
        name="Stock ETL Pipeline",
        # Run immediately on startup instead of waiting one full interval.
        next_run_time=datetime.now(timezone.utc),
        # If a run takes longer than the interval, don't queue another one.
        # Just wait for the current run to finish and then start the timer again.
        max_instances=1,
        coalesce=True,
    )

    logger.info(
        f"Scheduler started. Pipeline will run every {FETCH_INTERVAL_SECONDS}s. "
        f"Press Ctrl+C to stop."
    )

    # Register shutdown handler for clean Ctrl+C and Docker SIGTERM.
    # Without this, the scheduler might not flush the last log lines
    # or close DB connections cleanly on shutdown.
    def shutdown(signum, frame):
        logger.info("Shutdown signal received. Stopping scheduler...")
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped. Goodbye.")
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Pipeline stopped by user.")


# -----------------------------------------------------------
# Entry point — run the full scheduled pipeline
# -----------------------------------------------------------
# Usage: python -m src.pipeline.scheduler
# -----------------------------------------------------------
if __name__ == "__main__":
    start()
