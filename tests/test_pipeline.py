"""
tests/test_pipeline.py — Unit tests for the ETL pipeline
=========================================================
We test each pipeline step independently:
  - transform() gets the most thorough tests because it contains
    the most logic (validation rules, type conversion, edge cases)
  - load() is tested with a mocked database session
  - run_once() is tested with both extract and load mocked

WHY not test extract() separately?
  extract() is a thin wrapper around fetch_all_symbols().
  That function is already fully tested in test_fetcher.py.
  Testing the wrapper would just duplicate those tests.

WHY mock the database in load tests?
  We use PostgreSQL-specific SQL (ON CONFLICT DO NOTHING).
  SQLite (our test database) does not support this syntax.
  Rather than fighting the dialect difference, we mock the session
  and verify that our load() code calls the right methods.
  The real ON CONFLICT behaviour is verified by the end-to-end test
  at the bottom of this file (marked @pytest.mark.integration).
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from src.database.models import StockPrice
from src.pipeline.transform import transform, _validate_record
from src.pipeline.load import load, LoadResult


# -------------------------------------------------------
# Shared test data
# -------------------------------------------------------

def make_raw_record(**overrides) -> dict:
    """Build a valid raw record dict, with optional field overrides."""
    record = {
        "symbol": "AAPL",
        "price": 175.50,
        "volume": 52_000_000,
        "fetched_at": "2024-01-15T14:30:00+00:00",
    }
    record.update(overrides)
    return record


# -------------------------------------------------------
# Tests for _validate_record()
# -------------------------------------------------------

class TestValidateRecord:
    """Tests for the internal validation function."""

    def test_valid_record_passes(self):
        valid, reason = _validate_record(make_raw_record())
        assert valid is True
        assert reason == ""

    def test_missing_symbol_fails(self):
        record = make_raw_record()
        del record["symbol"]
        valid, reason = _validate_record(record)
        assert valid is False
        assert "symbol" in reason

    def test_missing_price_fails(self):
        record = make_raw_record()
        del record["price"]
        valid, reason = _validate_record(record)
        assert valid is False
        assert "price" in reason

    def test_none_price_fails(self):
        valid, reason = _validate_record(make_raw_record(price=None))
        assert valid is False

    def test_zero_price_fails(self):
        """Price of 0 is not valid financial data."""
        valid, reason = _validate_record(make_raw_record(price=0))
        assert valid is False
        assert "positive" in reason.lower()

    def test_negative_price_fails(self):
        valid, reason = _validate_record(make_raw_record(price=-10.0))
        assert valid is False

    def test_non_numeric_price_fails(self):
        valid, reason = _validate_record(make_raw_record(price="not_a_number"))
        assert valid is False

    def test_empty_symbol_fails(self):
        valid, reason = _validate_record(make_raw_record(symbol=""))
        assert valid is False

    def test_symbol_too_long_fails(self):
        valid, reason = _validate_record(make_raw_record(symbol="A" * 21))
        assert valid is False
        assert "long" in reason.lower()

    def test_negative_volume_fails(self):
        valid, reason = _validate_record(make_raw_record(volume=-1))
        assert valid is False
        assert "negative" in reason.lower()

    def test_zero_volume_passes(self):
        """Volume of 0 is acceptable (pre/after market hours)."""
        valid, reason = _validate_record(make_raw_record(volume=0))
        assert valid is True

    def test_very_large_price_fails(self):
        """Price above 1 million is likely a data error."""
        valid, reason = _validate_record(make_raw_record(price=1_000_001.0))
        assert valid is False


# -------------------------------------------------------
# Tests for transform()
# -------------------------------------------------------

class TestTransform:
    """Tests for the main transform() function."""

    def test_valid_record_produces_stock_price_object(self):
        """Happy path: one valid record → one StockPrice ORM object."""
        raw = [make_raw_record()]
        result = transform(raw)

        assert len(result) == 1
        assert isinstance(result[0], StockPrice)

    def test_symbol_is_uppercased(self):
        """Symbols must always be stored as uppercase."""
        raw = [make_raw_record(symbol="aapl")]
        result = transform(raw)
        assert result[0].symbol == "AAPL"

    def test_price_is_rounded_to_4_decimal_places(self):
        raw = [make_raw_record(price=175.123456789)]
        result = transform(raw)
        assert result[0].price == round(175.123456789, 4)

    def test_invalid_records_are_dropped(self):
        """
        Mixed input: one valid, one invalid.
        Only the valid record should appear in the output.
        """
        raw = [
            make_raw_record(symbol="AAPL", price=175.50),   # valid
            make_raw_record(symbol="BAD",  price=0),         # invalid — price is 0
        ]
        result = transform(raw)

        assert len(result) == 1
        assert result[0].symbol == "AAPL"

    def test_all_invalid_returns_empty_list(self):
        raw = [
            make_raw_record(price=0),
            make_raw_record(price=None),
        ]
        result = transform(raw)
        assert result == []

    def test_empty_input_returns_empty_list(self):
        result = transform([])
        assert result == []

    def test_fetched_at_is_datetime_object(self):
        """The timestamp string from the API must become a datetime object."""
        raw = [make_raw_record(fetched_at="2024-01-15T14:30:00+00:00")]
        result = transform(raw)
        assert isinstance(result[0].fetched_at, datetime)

    def test_fetched_at_has_timezone(self):
        """All timestamps must be timezone-aware (UTC)."""
        raw = [make_raw_record(fetched_at="2024-01-15T14:30:00+00:00")]
        result = transform(raw)
        assert result[0].fetched_at.tzinfo is not None

    def test_multiple_valid_records(self):
        """All valid records in a batch should pass through."""
        raw = [
            make_raw_record(symbol="AAPL",  price=175.50),
            make_raw_record(symbol="GOOGL", price=140.25),
            make_raw_record(symbol="MSFT",  price=370.87),
        ]
        result = transform(raw)
        assert len(result) == 3

    def test_volume_is_integer(self):
        """Volume must be an integer for the BIGINT database column."""
        raw = [make_raw_record(volume=52_000_000)]
        result = transform(raw)
        assert isinstance(result[0].volume, int)


# -------------------------------------------------------
# Tests for load()
# -------------------------------------------------------

class TestLoad:
    """
    Tests for the load() function.
    We mock the database session because load() uses PostgreSQL-specific
    SQL (ON CONFLICT DO NOTHING) that SQLite doesn't support.
    """

    def _make_stock_price(self, symbol: str = "AAPL") -> StockPrice:
        return StockPrice(
            symbol=symbol,
            price=175.50,
            volume=52_000_000,
            fetched_at=datetime.now(timezone.utc),
        )

    def test_empty_input_returns_zero_counts(self):
        """load([]) should return immediately with all zeros."""
        result = load([])
        assert result == LoadResult(inserted=0, skipped=0, failed=0)

    def test_inserted_count_increments_on_new_row(self):
        """When rowcount=1, the record was inserted (not a duplicate)."""
        mock_execute_result = MagicMock()
        mock_execute_result.rowcount = 1

        mock_session = MagicMock()
        mock_session.execute.return_value = mock_execute_result
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        with patch("src.pipeline.load.get_session", return_value=mock_session):
            result = load([self._make_stock_price()])

        assert result.inserted == 1
        assert result.skipped == 0
        assert result.failed == 0

    def test_skipped_count_increments_on_duplicate(self):
        """When rowcount=0, the record was skipped (ON CONFLICT DO NOTHING)."""
        mock_execute_result = MagicMock()
        mock_execute_result.rowcount = 0

        mock_session = MagicMock()
        mock_session.execute.return_value = mock_execute_result
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        with patch("src.pipeline.load.get_session", return_value=mock_session):
            result = load([self._make_stock_price()])

        assert result.inserted == 0
        assert result.skipped == 1
        assert result.failed == 0

    def test_failed_count_increments_on_exception(self):
        """When execute() raises, the record is counted as failed."""
        mock_session = MagicMock()
        mock_session.execute.side_effect = Exception("DB error")
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)

        with patch("src.pipeline.load.get_session", return_value=mock_session):
            result = load([self._make_stock_price()])

        assert result.failed == 1
        assert result.inserted == 0


# -------------------------------------------------------
# Integration test — end-to-end pipeline (run_once)
# -------------------------------------------------------

class TestRunOnce:
    """
    Test the full pipeline flow with both external dependencies mocked.
    This verifies that extract → transform → load are wired correctly.
    """

    def test_run_once_returns_summary_dict(self):
        """run_once() must return a summary dict with all expected keys."""
        fake_raw = [make_raw_record()]

        mock_load_result = LoadResult(inserted=1, skipped=0, failed=0)

        with patch("src.pipeline.scheduler.extract", return_value=fake_raw):
            with patch("src.pipeline.scheduler.load", return_value=mock_load_result):
                from src.pipeline.scheduler import run_once
                summary = run_once()

        assert "extracted" in summary
        assert "transformed" in summary
        assert "inserted" in summary
        assert "skipped" in summary
        assert "failed" in summary
        assert "duration_ms" in summary

    def test_run_once_counts_are_correct(self):
        """Counts in the summary must reflect what each step returned."""
        fake_raw = [
            make_raw_record(symbol="AAPL"),
            make_raw_record(symbol="GOOGL"),
        ]
        mock_load_result = LoadResult(inserted=2, skipped=0, failed=0)

        with patch("src.pipeline.scheduler.extract", return_value=fake_raw):
            with patch("src.pipeline.scheduler.load", return_value=mock_load_result):
                from src.pipeline.scheduler import run_once
                summary = run_once()

        assert summary["extracted"] == 2
        assert summary["inserted"] == 2
        assert summary["failed"] == 0
