"""
src/ingestion/fetcher.py — Live stock price fetcher
====================================================
This module has exactly ONE job: fetch raw stock price data
from Yahoo Finance and return it as Python dicts.

It does NOT:
  - Store data (that is the database layer's job)
  - Clean or validate data (that is the transform layer's job)
  - Schedule runs (that is the scheduler's job)

WHY this strict separation?
  - Each piece is independently testable
  - You can swap Yahoo Finance for another source by only
    changing THIS file — nothing else breaks
  - When something goes wrong, it is immediately obvious
    which layer failed (fetch? transform? store?)

WHY Yahoo Finance (yfinance)?
  - Completely free, no API key or account required
  - Returns real, live market data
  - Well-maintained Python library with pandas integration
  - Easy to understand for beginners

COMMON BEGINNER MISTAKE:
  Putting database writes inside the fetch function.
  "I'll just save it here while I have it."
  This makes the code untestable and impossible to change later.
  Keep fetch logic and storage logic completely separate.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

import yfinance as yf

from src.config import STOCK_SYMBOLS

# Get a logger named after this module: "src.ingestion.fetcher"
# This name appears in every log line so you know exactly
# which file produced each message.
logger = logging.getLogger(__name__)


def fetch_current_price(symbol: str) -> Optional[dict]:
    """
    Fetch the most recent price for a single stock symbol.

    Uses yfinance's fast_info property which returns the latest
    available price without downloading full history. This is
    significantly faster and lighter than downloading OHLCV data.

    Args:
        symbol: Stock ticker symbol, e.g. "AAPL", "GOOGL", "BTC-USD"

    Returns:
        A dict with keys: symbol, price, volume, fetched_at
        Returns None if the fetch fails for any reason.

    Why return None instead of raising an exception?
        In a pipeline that fetches 10 symbols, one bad symbol
        should not crash the entire run. We log the error and
        return None so the caller can skip it gracefully.
    """
    try:
        logger.info(f"Fetching price for {symbol}...")

        # yf.Ticker creates a Ticker object for the given symbol.
        # No network call happens here yet — it is just an object.
        ticker = yf.Ticker(symbol)

        # WHY ticker.history() instead of ticker.fast_info?
        #
        # fast_info reverse-engineers an unofficial Yahoo Finance endpoint
        # that changes frequently without notice. It breaks several times
        # per year as Yahoo updates their internal API.
        #
        # ticker.history() uses a more stable endpoint that has been
        # consistent for years. It returns OHLCV data (Open, High, Low,
        # Close, Volume) for the requested period.
        #
        # period="5d"  → fetch up to 5 days of daily bars
        # interval="1d" → one bar per day (daily close price)
        # We take the LAST row, which is the most recent trading day.
        # Using 5d (not 1d) ensures we get data even on weekends/holidays
        # when "today" has no data yet.
        hist = ticker.history(period="5d", interval="1d")

        # If the DataFrame is empty, the symbol is invalid or
        # Yahoo Finance has no data for it.
        if hist.empty:
            logger.warning(
                f"No price history returned for '{symbol}'. "
                f"The symbol may be invalid or delisted."
            )
            return None

        # Take the most recent row (last trading day)
        latest = hist.iloc[-1]
        price = float(latest["Close"])
        volume = int(latest["Volume"]) if latest["Volume"] is not None else 0

        # Validate: Close price must be positive
        if price <= 0:
            logger.warning(f"Invalid price ({price}) returned for '{symbol}'.")
            return None

        result = {
            # Always store symbols in uppercase for consistency
            "symbol": symbol.strip().upper(),

            # Round to 4 decimal places (important for crypto prices like BTC)
            "price": round(price, 4),

            # Volume can be 0 outside market hours — that is acceptable
            "volume": volume,

            # Always use UTC timestamps in a data pipeline.
            # Never store local time — it causes chaos when deploying
            # to servers in different timezones.
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }

        logger.info(f"  {result['symbol']}: ${result['price']:,.2f}  (volume: {result['volume']:,})")
        return result

    except Exception as e:
        # Catch everything: network errors, parsing errors, API changes.
        # Log clearly and return None so the pipeline keeps running.
        logger.error(f"Failed to fetch price for '{symbol}': {type(e).__name__}: {e}")
        return None


def fetch_all_symbols(symbols: Optional[list[str]] = None) -> list[dict]:
    """
    Fetch current prices for a list of stock symbols.

    Iterates through each symbol, calling fetch_current_price().
    Symbols that fail are logged and excluded from the result —
    they do not cause the entire batch to fail.

    Args:
        symbols: List of ticker symbols to fetch.
                 Defaults to STOCK_SYMBOLS from config (loaded from .env).

    Returns:
        List of successfully fetched price dicts.
        Empty list if all fetches fail.

    Example:
        >>> prices = fetch_all_symbols(["AAPL", "GOOGL"])
        >>> print(prices[0])
        {'symbol': 'AAPL', 'price': 175.5, 'volume': 52000000, 'fetched_at': '...'}
    """
    # Use the symbols from config if none are explicitly provided.
    # This is a common Python pattern: None as a default argument
    # instead of [] because mutable defaults in Python are shared
    # across all calls (a famous beginner gotcha).
    if symbols is None:
        symbols = STOCK_SYMBOLS

    if not symbols:
        logger.warning("No symbols configured. Set STOCK_SYMBOLS in your .env file.")
        return []

    logger.info(f"Starting fetch for {len(symbols)} symbol(s): {', '.join(symbols)}")

    results = []
    for symbol in symbols:
        data = fetch_current_price(symbol)
        if data is not None:
            results.append(data)

    # Summary log: useful to see at a glance how many succeeded
    success_count = len(results)
    total_count = len(symbols)

    if success_count == total_count:
        logger.info(f"All {total_count} symbols fetched successfully.")
    else:
        failed = total_count - success_count
        logger.warning(f"Fetched {success_count}/{total_count} symbols. {failed} failed.")

    return results


# -------------------------------------------------------
# Manual test — run this file directly to see live prices
# -------------------------------------------------------
# This block only executes when you run the file directly:
#   python src/ingestion/fetcher.py
#
# It does NOT run when the module is imported by other code.
# This is called an "entry point guard" — a common Python pattern.
if __name__ == "__main__":
    print("\n" + "=" * 50)
    print("  Stock Price Fetcher — Live Test")
    print("=" * 50 + "\n")

    prices = fetch_all_symbols()

    if prices:
        print(f"  {'Symbol':<10} {'Price':>12}   {'Volume':>15}   Timestamp")
        print("  " + "-" * 65)
        for item in prices:
            print(
                f"  {item['symbol']:<10} "
                f"${item['price']:>11,.2f}   "
                f"{item['volume']:>15,}   "
                f"{item['fetched_at']}"
            )
        print(f"\n  Fetched {len(prices)} prices successfully.\n")
    else:
        print("  No data returned.")
        print("  Check your internet connection and try again.\n")
