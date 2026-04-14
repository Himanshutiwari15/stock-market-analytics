"""
src/alerts/runner.py — Alert pipeline entry point
==================================================
WHAT THIS MODULE DOES
---------------------
This is the "glue" script that ties the anomaly detector and email
alerter together. It can be run two ways:

  1. ONE-SHOT (for testing / manual runs):
       python -m src.alerts.runner --once

  2. LOOP (for the Docker service — runs every N seconds forever):
       python -m src.alerts.runner

HOW IT WORKS (one cycle)
-------------------------
  1. Open a database session
  2. Ask anomaly_detector to scan all configured symbols
  3. If anomalies found → ask email_alerter to send an email
  4. Log a summary of what happened
  5. Sleep for FETCH_INTERVAL_SECONDS, then repeat

DESIGN DECISION: SEPARATE SERVICE IN DOCKER
--------------------------------------------
We run the alert runner as a SEPARATE Docker service (not inside the
main `app` service). Why?
  - Separation of concerns: ingestion (app) and alerting are distinct jobs
  - Independent restart: if alerts crash, ingestion keeps running
  - Easier to disable: just remove the `alerts` service from compose
  - Future-proof: you could replace this with a dedicated alerting tool
    (PagerDuty, Grafana Alerting, etc.) without touching the main app
"""

import argparse
import logging
import sys
import time

from src.alerts.anomaly_detector import detect_anomalies
from src.alerts.email_alerter import send_alert_email
from src.config import (
    ALERT_RECIPIENT,
    ANOMALY_LOOKBACK_DAYS,
    ANOMALY_Z_SCORE_THRESHOLD,
    FETCH_INTERVAL_SECONDS,
    SMTP_HOST,
    SMTP_PASSWORD,
    SMTP_PORT,
    SMTP_USER,
    STOCK_SYMBOLS,
)
from src.database.connection import get_session

logger = logging.getLogger(__name__)


def run_once() -> list:
    """
    Execute one full detection + alert cycle.

    Returns the list of Anomaly objects found (empty list if none).
    This return value is primarily useful for testing and one-shot runs.
    """
    logger.info("Starting anomaly detection cycle...")
    logger.info("Checking symbols: %s", ", ".join(STOCK_SYMBOLS))
    logger.info(
        "Parameters: lookback=%d days, z_threshold=%.1f",
        ANOMALY_LOOKBACK_DAYS,
        ANOMALY_Z_SCORE_THRESHOLD,
    )

    # Open a database session for this cycle.
    # The `with` block commits on success, rolls back on error, always closes.
    with get_session() as session:
        anomalies = detect_anomalies(
            session=session,
            symbols=STOCK_SYMBOLS,
            lookback_days=ANOMALY_LOOKBACK_DAYS,
            z_threshold=ANOMALY_Z_SCORE_THRESHOLD,
        )

    if anomalies:
        logger.info("Found %d anomaly/anomalies. Sending email alert...", len(anomalies))
        sent = send_alert_email(
            anomalies=anomalies,
            smtp_user=SMTP_USER,
            smtp_password=SMTP_PASSWORD,
            recipient=ALERT_RECIPIENT,
            smtp_host=SMTP_HOST,
            smtp_port=SMTP_PORT,
        )
        if sent:
            logger.info("Alert email sent successfully.")
        else:
            logger.warning(
                "Email was NOT sent (check SMTP credentials in .env). "
                "Anomalies were still logged above."
            )
    else:
        logger.info("No anomalies detected — no email sent.")

    return anomalies


def run_loop() -> None:
    """
    Run detection + alert in an infinite loop, sleeping between cycles.
    This is what the Docker `alerts` service calls.

    Sleep duration = FETCH_INTERVAL_SECONDS (same as the ETL pipeline)
    so alerts are checked every time new prices are fetched.

    Handles keyboard interrupts (Ctrl+C) cleanly so Docker can stop
    the container gracefully without a stack trace.
    """
    logger.info("Alert runner starting in LOOP mode.")
    logger.info("Check interval: %d seconds.", FETCH_INTERVAL_SECONDS)
    logger.info("Press Ctrl+C to stop.")

    while True:
        try:
            run_once()  # return value not used in loop mode
        except Exception as exc:
            # Log the error but DON'T crash the loop.
            # A transient DB outage or network error shouldn't kill the alerter.
            logger.error("Error in detection cycle (will retry next interval): %s", exc)

        logger.info("Sleeping %d seconds until next check...", FETCH_INTERVAL_SECONDS)
        time.sleep(FETCH_INTERVAL_SECONDS)


def main() -> None:
    """
    Parse command-line arguments and dispatch to run_once or run_loop.

    --once flag: run exactly one cycle and exit.
                 Useful for testing: `python -m src.alerts.runner --once`
    No flag:     run forever (loop mode, for the Docker service).
    """
    parser = argparse.ArgumentParser(
        description="Stock market anomaly detection and email alert runner."
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run exactly one detection cycle and exit (useful for testing).",
    )
    args = parser.parse_args()

    if args.once:
        logger.info("Running in ONE-SHOT mode.")
        run_once()
        # Exit code 0 = success (even if no anomalies).
        # This is correct for CI/scheduled jobs: success means "ran cleanly".
        sys.exit(0)
    else:
        run_loop()


if __name__ == "__main__":
    main()
