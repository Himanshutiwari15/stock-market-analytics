"""
src/alerts/anomaly_detector.py — Z-score based price anomaly detection
=======================================================================
WHAT THIS MODULE DOES
---------------------
It looks at the recent price history for each stock symbol and asks:
"Is today's price unusually far from the recent average?"

We answer that with a Z-score:

    z = (latest_price - mean_of_last_N_days) / std_dev_of_last_N_days

If the absolute value of z exceeds our threshold (default 2.5), we flag
the symbol as anomalous and record it for alerting.

WHY Z-SCORE INSTEAD OF A SIMPLE PERCENT CHANGE?
-------------------------------------------------
A 3% move on TSLA is routine (it's volatile). A 3% move on AAPL is
extraordinary. A fixed percent threshold would either spam TSLA alerts
or miss AAPL events.

Z-score is self-normalising — it's relative to *that stock's own*
recent variability. If TSLA's 20-day std dev is 4%, a 3% move has a
low z-score (not anomalous). If AAPL's std dev is 1%, a 3% move has a
high z-score (genuinely unusual).

DEPENDENCIES
------------
- sqlalchemy session: injected by the caller (not created here)
  WHY? Makes it easy to mock in tests without touching a real DB.
- Python's stdlib `statistics` module: no external dependencies.
"""

import logging
import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from src.database.models import StockPrice

logger = logging.getLogger(__name__)


@dataclass
class Anomaly:
    """
    Represents a detected price anomaly for one stock symbol.

    We use a dataclass instead of a plain dict because:
    - Attribute access (anomaly.symbol) is cleaner than dict access (d["symbol"])
    - The type annotations act as documentation
    - repr() is auto-generated for easy logging/debugging
    """
    symbol: str          # e.g. "AAPL"
    latest_price: float  # the price that triggered the alert
    mean: float          # mean of the lookback window
    stdev: float         # standard deviation of the lookback window
    z_score: float       # how many std devs away from mean (signed)
    direction: str       # "spike" (price up) or "drop" (price down)
    detected_at: datetime  # timestamp of the anomalous price record
    sample_size: int     # how many historical rows were used


def detect_anomalies(
    session: Session,
    symbols: list[str],
    lookback_days: int = 20,
    z_threshold: float = 2.5,
    reference_time: datetime | None = None,
) -> list[Anomaly]:
    """
    Scan the database for anomalous price movements.

    For each symbol:
      1. Fetch all price rows from the last `lookback_days` days.
      2. Separate the most-recent row (candidate) from the rest (baseline).
      3. Compute mean + std dev of the baseline prices.
      4. Compute z-score of the candidate price.
      5. If |z-score| > z_threshold → it's an anomaly.

    Args:
        session:        SQLAlchemy session (injected — not created here).
        symbols:        List of ticker symbols to check (e.g. ["AAPL", "TSLA"]).
        lookback_days:  How many days of history to use as the baseline.
        z_threshold:    Flag as anomaly if |z-score| exceeds this value.
        reference_time: The "now" to use when computing the lookback window.
                        Defaults to UTC now. Inject a fixed time in tests.

    Returns:
        List of Anomaly objects — one per symbol that exceeded the threshold.
        Returns an empty list if no anomalies were found.
    """
    if reference_time is None:
        reference_time = datetime.now(timezone.utc)

    # The earliest timestamp we'll include in our lookback window.
    since = reference_time - timedelta(days=lookback_days)

    anomalies: list[Anomaly] = []

    for symbol in symbols:
        logger.debug("Checking %s for anomalies (lookback=%d days)...", symbol, lookback_days)

        # Fetch rows for this symbol within the lookback window.
        # We order ascending so the LAST row is the most recent price.
        rows = (
            session.query(StockPrice)
            .filter(
                StockPrice.symbol == symbol,
                StockPrice.fetched_at >= since,
            )
            .order_by(StockPrice.fetched_at.asc())
            .all()
        )

        # Need at least 3 rows: 2 for the baseline + 1 as the candidate.
        # With fewer rows we can't compute a meaningful standard deviation.
        if len(rows) < 3:
            logger.debug(
                "  %s: only %d rows in window — skipping (need ≥ 3).",
                symbol, len(rows)
            )
            continue

        # The most recent row is the "candidate" we're testing.
        # Everything before it forms the "baseline" for statistics.
        candidate_row = rows[-1]
        baseline_rows = rows[:-1]

        candidate_price = float(candidate_row.price)
        baseline_prices = [float(r.price) for r in baseline_rows]

        # Compute baseline statistics.
        mean = statistics.mean(baseline_prices)

        # statistics.stdev uses sample std dev (divides by n-1).
        # This gives a better estimate of population variance with small samples.
        stdev = statistics.stdev(baseline_prices)

        # Guard against a flat line (all prices identical → std dev = 0).
        # Division by zero would crash; a flat line also has no meaningful z-score.
        if stdev == 0:
            logger.debug("  %s: std dev is 0 — price is constant, skipping.", symbol)
            continue

        # The core formula.
        z_score = (candidate_price - mean) / stdev

        logger.debug(
            "  %s: price=%.4f  mean=%.4f  stdev=%.4f  z=%.2f",
            symbol, candidate_price, mean, stdev, z_score
        )

        # Flag if the absolute z-score exceeds our threshold.
        if abs(z_score) > z_threshold:
            direction = "spike" if z_score > 0 else "drop"
            anomaly = Anomaly(
                symbol=symbol,
                latest_price=candidate_price,
                mean=round(mean, 4),
                stdev=round(stdev, 4),
                z_score=round(z_score, 4),
                direction=direction,
                detected_at=candidate_row.fetched_at,
                sample_size=len(baseline_prices),
            )
            anomalies.append(anomaly)
            logger.warning(
                "ANOMALY detected: %s | price=%.4f | z=%.2f | direction=%s",
                symbol, candidate_price, z_score, direction
            )

    logger.info(
        "Anomaly scan complete: %d/%d symbols flagged.", len(anomalies), len(symbols)
    )
    return anomalies
