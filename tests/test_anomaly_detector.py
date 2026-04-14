"""
tests/test_anomaly_detector.py — Unit tests for the anomaly detector
=====================================================================
TESTING STRATEGY
----------------
We NEVER connect to a real database in unit tests. Instead, we use
unittest.mock to create a "fake" SQLAlchemy session that returns
controlled test data.

Why mock the session?
  - Speed: no network round-trip, no DB startup needed
  - Isolation: tests work in CI with no PostgreSQL container
  - Control: we can simulate exactly the data we want

We create StockPrice objects directly in Python (no DB required) and
stuff them into a mock query chain that returns them when called.

HOW THE MOCK QUERY CHAIN WORKS
--------------------------------
The detector calls:
    session.query(StockPrice).filter(...).order_by(...).all()

Each method returns an object with more methods — this is called a
"fluent interface" or "method chaining". To mock it:

    mock_session.query.return_value         = mock_query
    mock_query.filter.return_value          = mock_filter
    mock_filter.order_by.return_value       = mock_order
    mock_order.all.return_value             = [row1, row2, ...]

When the code calls session.query(...).filter(...).order_by(...).all(),
Python follows the chain and eventually returns our fake list.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from src.alerts.anomaly_detector import Anomaly, detect_anomalies
from src.database.models import StockPrice


# -----------------------------------------------------------------------
# HELPERS — build fake StockPrice rows
# -----------------------------------------------------------------------

def _make_prices(
    symbol: str,
    prices: list[float],
    base_time: datetime | None = None,
) -> list[StockPrice]:
    """
    Build a list of StockPrice objects with sequentially increasing timestamps.
    The last entry in `prices` becomes the most-recent (candidate) price.

    We don't insert into a DB — we just create Python objects.
    SQLAlchemy ORM objects work without a DB as long as you don't
    try to commit or flush them.
    """
    if base_time is None:
        base_time = datetime.now(timezone.utc)

    rows = []
    for i, p in enumerate(prices):
        row = StockPrice()
        row.symbol = symbol
        row.price = p
        row.volume = 1_000_000
        # Space rows 1 hour apart; most recent = base_time
        row.fetched_at = base_time - timedelta(hours=(len(prices) - 1 - i))
        rows.append(row)
    return rows


def _make_mock_session(rows: list[StockPrice]) -> MagicMock:
    """
    Build a MagicMock that mimics the SQLAlchemy session query chain.

    The detector calls:
        session.query(StockPrice).filter(...).order_by(...).all()

    We wire the chain so .all() returns `rows`.
    """
    mock_session = MagicMock()
    mock_query   = MagicMock()
    mock_filter  = MagicMock()
    mock_order   = MagicMock()

    mock_session.query.return_value   = mock_query
    mock_query.filter.return_value    = mock_filter
    mock_filter.order_by.return_value = mock_order
    mock_order.all.return_value       = rows

    return mock_session


# -----------------------------------------------------------------------
# TESTS
# -----------------------------------------------------------------------

class TestDetectAnomalies:
    """Tests for the detect_anomalies() function."""

    def test_no_anomaly_for_stable_prices(self):
        """
        HAPPY PATH: prices that barely move should NOT trigger an anomaly.

        We use 10 prices all clustered around 100.0 with tiny fluctuations.
        The latest price (100.3) is barely different from the mean — z-score
        will be well below 2.5.
        """
        stable_prices = [100.0, 100.1, 99.9, 100.2, 100.0,
                         99.8, 100.1, 100.3, 100.0, 100.1]
        # last price is 100.1 — the "latest" (candidate)
        rows = _make_prices("AAPL", stable_prices)
        session = _make_mock_session(rows)

        anomalies = detect_anomalies(session, ["AAPL"], z_threshold=2.5)

        assert anomalies == [], (
            f"Expected no anomalies for stable prices, got: {anomalies}"
        )

    def test_spike_is_detected(self):
        """
        EDGE CASE: a large price spike should be flagged as an anomaly.

        We set up 9 prices with small natural variance around 100, then
        add a final price of 200.0 — roughly a 100% jump, producing a
        z-score >> 2.5.

        Important: the baseline must have SOME variance (stdev > 0),
        otherwise the zero-stdev guard skips the symbol.
        """
        # Small realistic variance in baseline (stdev ≈ 0.2), then a spike
        baseline = [99.8, 100.2, 99.9, 100.1, 100.0, 100.3, 99.7, 100.2, 100.1]
        spike_prices = baseline + [200.0]
        rows = _make_prices("TSLA", spike_prices)
        session = _make_mock_session(rows)

        anomalies = detect_anomalies(session, ["TSLA"], z_threshold=2.5)

        assert len(anomalies) == 1
        a = anomalies[0]
        assert a.symbol == "TSLA"
        assert a.direction == "spike"
        assert a.z_score > 2.5
        assert a.latest_price == 200.0

    def test_drop_is_detected(self):
        """
        EDGE CASE: a large price DROP should also be flagged.

        9 prices with small variance around 100, then a crash to 50.0.
        Z-score will be large and NEGATIVE → direction = "drop".
        """
        baseline = [99.8, 100.2, 99.9, 100.1, 100.0, 100.3, 99.7, 100.2, 100.1]
        drop_prices = baseline + [50.0]
        rows = _make_prices("GOOGL", drop_prices)
        session = _make_mock_session(rows)

        anomalies = detect_anomalies(session, ["GOOGL"], z_threshold=2.5)

        assert len(anomalies) == 1
        a = anomalies[0]
        assert a.symbol == "GOOGL"
        assert a.direction == "drop"
        assert a.z_score < -2.5  # negative z-score for a drop

    def test_insufficient_data_returns_empty(self):
        """
        EDGE CASE: fewer than 3 rows → can't compute stats → skip symbol.

        The detector needs at least 3 rows: 2 for baseline + 1 candidate.
        With only 2 rows we can't compute a meaningful standard deviation.
        """
        two_rows = _make_prices("MSFT", [150.0, 300.0])  # only 2 prices
        session = _make_mock_session(two_rows)

        anomalies = detect_anomalies(session, ["MSFT"], z_threshold=2.5)

        assert anomalies == [], (
            "Should return empty list when there are fewer than 3 data points"
        )

    def test_zero_std_dev_skipped(self):
        """
        EDGE CASE: all prices identical → std dev = 0 → skip (can't divide by 0).

        This can happen with illiquid stocks where price doesn't move for days.
        """
        flat_prices = [100.0] * 10  # perfectly flat
        rows = _make_prices("FLAT", flat_prices)
        session = _make_mock_session(rows)

        # Should not raise ZeroDivisionError — just silently skip
        anomalies = detect_anomalies(session, ["FLAT"], z_threshold=2.5)

        assert anomalies == []

    def test_multiple_symbols_independent(self):
        """
        Multiple symbols are checked independently.
        One anomalous + one normal → only the anomalous one is returned.
        """
        _baseline = [99.8, 100.2, 99.9, 100.1, 100.0, 100.3, 99.7, 100.2, 100.1]
        stable = _make_prices("AAPL", _baseline + [100.15])  # within noise
        spiked = _make_prices("TSLA", _baseline + [500.0])   # huge spike

        # Each call to session.query().filter().order_by().all() must return
        # the correct symbol's rows. We use side_effect to return different
        # data on successive calls.
        mock_session = MagicMock()
        mock_query   = MagicMock()
        mock_filter  = MagicMock()
        mock_order   = MagicMock()

        mock_session.query.return_value   = mock_query
        mock_query.filter.return_value    = mock_filter
        mock_filter.order_by.return_value = mock_order
        # First call → AAPL rows, second call → TSLA rows
        mock_order.all.side_effect = [stable, spiked]

        anomalies = detect_anomalies(mock_session, ["AAPL", "TSLA"], z_threshold=2.5)

        assert len(anomalies) == 1
        assert anomalies[0].symbol == "TSLA"

    def test_anomaly_fields_are_populated(self):
        """
        The Anomaly dataclass should have all fields correctly set.
        """
        baseline = [99.8, 100.2, 99.9, 100.1, 100.0, 100.3, 99.7, 100.2, 100.1]
        prices = baseline + [200.0]
        rows = _make_prices("AAPL", prices)
        session = _make_mock_session(rows)

        anomalies = detect_anomalies(session, ["AAPL"], z_threshold=2.5)

        assert len(anomalies) == 1
        a = anomalies[0]

        # All fields should be populated
        assert a.symbol == "AAPL"
        assert a.latest_price == 200.0
        assert a.mean > 0
        assert a.stdev > 0
        assert a.detected_at is not None
        assert a.sample_size == 9   # 9 baseline rows (10 total - 1 candidate)
        assert a.direction == "spike"

    def test_empty_symbols_list(self):
        """Edge case: no symbols to check → return empty list immediately."""
        session = _make_mock_session([])

        anomalies = detect_anomalies(session, symbols=[], z_threshold=2.5)

        assert anomalies == []
        # session.query should never have been called
        session.query.assert_not_called()
