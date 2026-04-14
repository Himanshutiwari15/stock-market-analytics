"""
tests/test_fetcher.py — Unit tests for the stock data fetcher
=============================================================
These are UNIT tests. That means they test our code in isolation,
with all external dependencies replaced by fakes (mocks).

WHY mock the Yahoo Finance API?
  1. Speed: real API calls take 1-3 seconds each. With mocks, 5 tests
     run in under 0.1 seconds. At scale, this matters enormously.
  2. Reliability: CI servers have no guarantee of internet access.
     Tests that require the internet are "flaky" — they pass sometimes
     and fail for reasons unrelated to your code.
  3. Control: we can simulate scenarios that are hard to reproduce
     with real data (e.g. an API returning 0 for a price).
  4. Focus: we're testing OUR logic — error handling, data formatting,
     None filtering — not whether Yahoo Finance's servers are up.

HOW mocking works (the key concept):
  - The real code calls: yf.Ticker("AAPL").fast_info.last_price
  - In tests, we use patch() to intercept that call and return
    a fake object with values we control.
  - The code under test never knows it's talking to a fake.
  - After the test, the real yf.Ticker is restored automatically.

STRUCTURE:
  We group related tests into classes for organisation.
  - TestFetchCurrentPrice: tests for the single-symbol function
  - TestFetchAllSymbols: tests for the batch function
"""

from unittest.mock import MagicMock, patch

import pytest

from src.ingestion.fetcher import fetch_all_symbols, fetch_current_price


# -------------------------------------------------------
# Tests for fetch_current_price()
# -------------------------------------------------------

def _make_mock_ticker(close_price: float, volume: int):
    """
    Helper: builds a mock yf.Ticker whose .history() returns a
    single-row DataFrame with the given Close and Volume values.

    We switched from fast_info to ticker.history() because fast_info
    breaks whenever Yahoo Finance changes their internal API.
    history() uses a more stable endpoint and has been consistent
    for years. These tests mock history() to match that change.
    """
    import pandas as pd

    # Build a minimal DataFrame that looks like real yfinance output
    df = pd.DataFrame(
        {"Close": [close_price], "Volume": [volume]},
        index=pd.to_datetime(["2024-01-15"]),
    )
    mock_ticker = MagicMock()
    mock_ticker.history.return_value = df
    return mock_ticker


def _make_empty_ticker():
    """Helper: builds a mock yf.Ticker whose .history() returns an empty DataFrame."""
    import pandas as pd

    mock_ticker = MagicMock()
    mock_ticker.history.return_value = pd.DataFrame()
    return mock_ticker


class TestFetchCurrentPrice:
    """Tests for the fetch_current_price(symbol) function."""

    def test_returns_dict_with_correct_structure(self):
        """
        Happy path: a valid symbol with real history data returns a
        dict with exactly the keys downstream code relies on.
        """
        mock_ticker = _make_mock_ticker(close_price=175.50, volume=52_000_000)

        with patch("src.ingestion.fetcher.yf.Ticker", return_value=mock_ticker):
            result = fetch_current_price("AAPL")

        assert result is not None
        assert result["symbol"] == "AAPL"
        assert result["price"] == 175.50
        assert result["volume"] == 52_000_000
        assert "fetched_at" in result

    def test_price_is_rounded_to_4_decimal_places(self):
        """
        Data quality: prices must be rounded consistently.
        This matters for crypto (e.g. BTC = 43251.00012345678).
        """
        mock_ticker = _make_mock_ticker(close_price=175.123456789, volume=1000)

        with patch("src.ingestion.fetcher.yf.Ticker", return_value=mock_ticker):
            result = fetch_current_price("AAPL")

        assert result["price"] == round(175.123456789, 4)

    def test_symbol_is_always_uppercased(self):
        """
        Normalisation: a user might pass "aapl" or "Aapl".
        We always store symbols in uppercase to prevent duplicate DB rows.
        """
        mock_ticker = _make_mock_ticker(close_price=175.50, volume=1000)

        with patch("src.ingestion.fetcher.yf.Ticker", return_value=mock_ticker):
            result = fetch_current_price("aapl")  # lowercase input

        assert result["symbol"] == "AAPL"  # uppercase in output

    def test_returns_none_when_history_is_empty(self):
        """
        Data quality guard: an empty DataFrame means the symbol is
        invalid, delisted, or Yahoo Finance has no data for it.
        We must return None rather than crashing or storing bad data.
        """
        mock_ticker = _make_empty_ticker()

        with patch("src.ingestion.fetcher.yf.Ticker", return_value=mock_ticker):
            result = fetch_current_price("INVALID_SYMBOL")

        assert result is None

    def test_returns_none_when_price_is_zero(self):
        """
        Data quality guard: a Close price of 0 is not valid market data.
        Return None so zero-price rows never enter the database.
        """
        mock_ticker = _make_mock_ticker(close_price=0, volume=0)

        with patch("src.ingestion.fetcher.yf.Ticker", return_value=mock_ticker):
            result = fetch_current_price("AAPL")

        assert result is None

    def test_returns_none_on_network_exception(self):
        """
        Resilience: if yfinance raises any exception (network error,
        timeout, API change), the function must NOT crash the pipeline.
        It logs the error and returns None so the pipeline continues.
        """
        with patch(
            "src.ingestion.fetcher.yf.Ticker",
            side_effect=Exception("Connection timed out"),
        ):
            result = fetch_current_price("AAPL")

        assert result is None

    def test_volume_is_integer(self):
        """
        Type safety: volume must be an integer before DB insertion.
        yfinance sometimes returns floats (e.g. 52000000.0) — we cast.
        """
        mock_ticker = _make_mock_ticker(close_price=175.50, volume=52_000_000)

        with patch("src.ingestion.fetcher.yf.Ticker", return_value=mock_ticker):
            result = fetch_current_price("AAPL")

        assert isinstance(result["volume"], int)


# -------------------------------------------------------
# Tests for fetch_all_symbols()
# -------------------------------------------------------

class TestFetchAllSymbols:
    """Tests for the fetch_all_symbols(symbols) batch function."""

    def test_returns_all_successful_fetches(self):
        """
        Happy path: all symbols succeed, all results are returned.
        """
        fake_result = {
            "symbol": "AAPL",
            "price": 175.50,
            "volume": 1000,
            "fetched_at": "2024-01-15T14:30:00+00:00"
        }

        # Make fetch_current_price always return our fake result
        with patch(
            "src.ingestion.fetcher.fetch_current_price",
            return_value=fake_result
        ):
            results = fetch_all_symbols(["AAPL", "GOOGL"])

        # Both symbols returned data, so we expect 2 results
        assert len(results) == 2

    def test_skips_failed_symbols_and_returns_rest(self):
        """
        Resilience: if one symbol fails, the others still return.
        This is critical — a broken symbol should never block good data.
        """
        def mock_fetch(symbol: str):
            if symbol == "AAPL":
                return {
                    "symbol": "AAPL", "price": 175.50,
                    "volume": 1000, "fetched_at": "2024-01-15T14:30:00+00:00"
                }
            return None  # GOOGL "fails" to fetch

        with patch("src.ingestion.fetcher.fetch_current_price", side_effect=mock_fetch):
            results = fetch_all_symbols(["AAPL", "GOOGL"])

        # Only AAPL succeeded
        assert len(results) == 1
        assert results[0]["symbol"] == "AAPL"

    def test_returns_empty_list_when_all_fail(self):
        """
        Worst case: every symbol fails. Should return [] not raise.
        An empty list is a valid, safe return value.
        """
        with patch(
            "src.ingestion.fetcher.fetch_current_price",
            return_value=None  # every call fails
        ):
            results = fetch_all_symbols(["AAPL", "GOOGL", "MSFT"])

        assert results == []

    def test_uses_config_symbols_when_no_argument_given(self):
        """
        Default behaviour: when called with no arguments, it uses
        the STOCK_SYMBOLS list from config (which comes from .env).
        We patch STOCK_SYMBOLS to ["TEST"] to control what is fetched.
        """
        with patch("src.ingestion.fetcher.STOCK_SYMBOLS", ["TEST"]):
            with patch(
                "src.ingestion.fetcher.fetch_current_price",
                return_value=None
            ) as mock_fetch:
                fetch_all_symbols()  # no argument — should use config

        # fetch_current_price should have been called once with "TEST"
        mock_fetch.assert_called_once_with("TEST")

    def test_returns_empty_list_for_empty_input(self):
        """
        Edge case: calling with an empty list should return [] immediately.
        """
        results = fetch_all_symbols([])
        assert results == []
