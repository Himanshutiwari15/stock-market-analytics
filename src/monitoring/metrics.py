"""
src/monitoring/metrics.py — Prometheus metrics definitions
==========================================================
WHAT IS PROMETHEUS?
  Prometheus is a monitoring tool. It works by "scraping" — periodically
  calling an HTTP endpoint (/metrics) on your app and reading a list of
  named numbers (metrics).

  Your app doesn't push data to Prometheus. Prometheus pulls it.
  This means if your app crashes, Prometheus notices immediately because
  the scrape fails.

METRIC TYPES (the four you need to know):
  Counter   — only goes up. Never resets unless the process restarts.
              Example: total requests served, total records inserted.
  Gauge     — can go up or down. Represents a current value.
              Example: last run duration, queue depth, pipeline_up (0/1).
  Histogram — records the distribution of values (fast/slow runs).
              Example: run duration percentiles (p50, p95, p99).
  Summary   — like Histogram but computed client-side (less common).

  We use Counter and Gauge here. Simple, readable, effective.

HOW THE HTTP SERVER WORKS:
  start_metrics_server() calls prometheus_client.start_http_server(8000).
  This spawns a background thread (not a separate process) that listens
  on port 8000 and serves the /metrics endpoint.
  The endpoint returns plain text like:
    # HELP pipeline_up 1 if the pipeline is running, 0 if it is down
    # TYPE pipeline_up gauge
    pipeline_up 1.0
    pipeline_last_run_duration_seconds 0.497
    ...
  Prometheus scrapes that URL every 15 seconds and stores the values
  as time-series data. Grafana then queries Prometheus to draw graphs.

USAGE in scheduler.py:
  from src.monitoring.metrics import (
      PIPELINE_RUNS, PIPELINE_RECORDS_INSERTED, ...
      start_metrics_server,
  )
"""

import logging

from prometheus_client import Counter, Gauge, start_http_server

logger = logging.getLogger(__name__)

# -------------------------------------------------------
# Metric: pipeline health indicator
# -------------------------------------------------------
# PIPELINE_UP is a Gauge that equals 1 when the pipeline is running
# normally and 0 when it has crashed or failed its last run.
# This is the most important metric — you can set a Grafana alert
# that fires when pipeline_up == 0 for more than N minutes.
PIPELINE_UP = Gauge(
    "pipeline_up",
    "1 if the pipeline is running normally, 0 if it has errors",
)

# -------------------------------------------------------
# Metric: count of pipeline runs by outcome
# -------------------------------------------------------
# Labels let one metric track multiple categories.
# pipeline_runs_total{status="success"} → successful runs
# pipeline_runs_total{status="failed"}  → failed runs
# In Grafana/PromQL: rate(pipeline_runs_total{status="success"}[5m])
PIPELINE_RUNS = Counter(
    "pipeline_runs_total",
    "Total number of ETL pipeline runs completed",
    ["status"],  # label name: values will be "success" or "failed"
)

# -------------------------------------------------------
# Metric: records inserted and skipped (running totals)
# -------------------------------------------------------
# Counters accumulate over the lifetime of the process.
# To get "records inserted in the last 5 minutes" in PromQL:
#   increase(pipeline_records_inserted_total[5m])
PIPELINE_RECORDS_INSERTED = Counter(
    "pipeline_records_inserted_total",
    "Total number of stock price records written to PostgreSQL",
)

PIPELINE_RECORDS_SKIPPED = Counter(
    "pipeline_records_skipped_total",
    "Total number of duplicate records skipped (already in the database)",
)

# -------------------------------------------------------
# Metric: performance of the most recent run
# -------------------------------------------------------
# Gauges reflect the CURRENT (most recent) value.
# Every successful run overwrites the previous value.
PIPELINE_LAST_DURATION = Gauge(
    "pipeline_last_run_duration_seconds",
    "Wall-clock duration of the most recent pipeline run, in seconds",
)

PIPELINE_LAST_INSERTED = Gauge(
    "pipeline_last_run_inserted",
    "Number of records inserted in the most recent pipeline run",
)


# -------------------------------------------------------
# Start the metrics HTTP server
# -------------------------------------------------------

def start_metrics_server(port: int = 8000) -> None:
    """
    Start the Prometheus metrics HTTP server on the given port.

    This spawns a background thread — it does NOT block.
    After this call, http://localhost:8000/metrics serves live metrics.

    Call this ONCE at application startup, before the scheduler starts.
    Calling it a second time would raise an OSError (port already in use).

    Args:
        port: TCP port to listen on. Must match:
              - docker-compose.yml app service ports section
              - prometheus.yml scrape target
    """
    start_http_server(port)
    logger.info(
        f"Prometheus metrics server started — "
        f"http://localhost:{port}/metrics"
    )
