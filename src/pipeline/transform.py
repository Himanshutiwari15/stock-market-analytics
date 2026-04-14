"""
src/pipeline/transform.py — Transform step of the ETL pipeline
===============================================================
The Transform step takes raw, untrusted data from the extract step
and produces clean, validated, typed records ready for the database.

WHY validation matters:
  Raw API data is not guaranteed to be correct. An API might return:
  - None instead of a price (market closed, symbol invalid)
  - A price of 0 (error condition, not a real price)
  - A string where a number is expected (API format change)
  - Missing keys (partial response due to network issue)

  If we insert these directly into the database, we end up with
  garbage data that silently corrupts our analytics. A price chart
  showing $0 for AAPL is worse than showing no data at all.

WHAT this step does:
  1. Validates each raw dict has all required fields
  2. Validates that values are within acceptable ranges
  3. Converts raw dicts → StockPrice ORM objects (typed Python objects)
  4. Discards invalid records and logs exactly why they were dropped
  5. Returns only the clean records

IDEMPOTENCY:
  transform() can be called multiple times with the same input and
  always returns the same output. It has no side effects (no DB writes,
  no API calls). This makes it trivial to test and safe to retry.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from src.database.models import StockPrice

logger = logging.getLogger(__name__)

# Maximum plausible stock price — anything above this is likely a data error.
# Even Berkshire Hathaway Class A (the most expensive stock) trades ~$600k.
# We use 1 million as a safe upper bound.
MAX_PRICE = 1_000_000.0

# Maximum plausible volume per fetch interval.
# Apple (highest volume stock) rarely exceeds 500M shares in a full day.
MAX_VOLUME = 10_000_000_000  # 10 billion


def _validate_record(record: dict) -> tuple[bool, str]:
    """
    Validate a single raw record from the extract step.

    Args:
        record: Raw dict from fetch_all_symbols()

    Returns:
        (True, "") if valid
        (False, "reason") if invalid

    WHY return a tuple instead of raising an exception?
        In a batch transform, one invalid record should not stop
        processing of the others. We return a reason string so
        the caller can log exactly WHY each record was rejected.
        This is the standard pattern for ETL validation.
    """
    # --- Check required fields exist ---
    required_fields = ["symbol", "price", "volume", "fetched_at"]
    for field in required_fields:
        if field not in record:
            return False, f"Missing required field: '{field}'"
        if record[field] is None:
            return False, f"Field '{field}' is None"

    # --- Validate symbol ---
    symbol = record["symbol"]
    if not isinstance(symbol, str):
        return False, f"Symbol must be a string, got {type(symbol).__name__}"
    if not symbol.strip():
        return False, "Symbol is empty"
    if len(symbol) > 20:
        return False, f"Symbol '{symbol}' is too long (max 20 chars)"

    # --- Validate price ---
    try:
        price = float(record["price"])
    except (TypeError, ValueError):
        return False, f"Price '{record['price']}' is not a valid number"

    if price <= 0:
        return False, f"Price must be positive, got {price}"
    if price > MAX_PRICE:
        return False, f"Price {price} exceeds maximum plausible value ({MAX_PRICE})"

    # --- Validate volume ---
    try:
        volume = int(record["volume"])
    except (TypeError, ValueError):
        return False, f"Volume '{record['volume']}' is not a valid integer"

    if volume < 0:
        return False, f"Volume cannot be negative, got {volume}"
    if volume > MAX_VOLUME:
        return False, f"Volume {volume} exceeds maximum plausible value ({MAX_VOLUME})"

    # --- Validate timestamp ---
    fetched_at = record["fetched_at"]
    if not isinstance(fetched_at, (str, datetime)):
        return False, f"fetched_at must be a string or datetime, got {type(fetched_at).__name__}"

    return True, ""


def _parse_timestamp(value: str | datetime) -> datetime:
    """
    Parse a timestamp string or pass through a datetime object.
    Always returns a timezone-aware datetime in UTC.
    """
    if isinstance(value, datetime):
        # If already a datetime but without timezone, assume UTC
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value

    # Parse ISO format string: "2024-01-15T14:30:00+00:00"
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        # If ISO parsing fails, use current UTC time as fallback
        logger.warning(f"Could not parse timestamp '{value}', using current UTC time.")
        return datetime.now(timezone.utc)


def transform(raw_records: list[dict]) -> list[StockPrice]:
    """
    Validate and convert raw price dicts into StockPrice ORM objects.

    Args:
        raw_records: List of dicts from the extract step.

    Returns:
        List of valid StockPrice objects, ready to be passed to load().
        Invalid records are logged and excluded — they do NOT raise exceptions.

    Example:
        raw = [{"symbol": "AAPL", "price": 175.50, "volume": 52000000, "fetched_at": "..."}]
        clean = transform(raw)
        # clean = [<StockPrice(symbol='AAPL', price=175.5000, ...)>]
    """
    if not raw_records:
        logger.warning("TRANSFORM: Received empty input — nothing to transform.")
        return []

    logger.info(f"TRANSFORM: Processing {len(raw_records)} raw record(s)...")

    clean_records: list[StockPrice] = []
    rejected_count = 0

    for record in raw_records:
        is_valid, reason = _validate_record(record)

        if not is_valid:
            logger.warning(
                f"TRANSFORM: Rejected record for '{record.get('symbol', 'UNKNOWN')}' "
                f"— {reason}"
            )
            rejected_count += 1
            continue

        # Convert the validated dict to a typed ORM object.
        # From this point on, the rest of the pipeline works with
        # Python objects, not raw dicts — safer and more readable.
        stock_price = StockPrice(
            symbol=record["symbol"].strip().upper(),
            price=round(float(record["price"]), 4),
            volume=int(record["volume"]),
            fetched_at=_parse_timestamp(record["fetched_at"]),
        )
        clean_records.append(stock_price)

    logger.info(
        f"TRANSFORM: {len(clean_records)} record(s) passed validation, "
        f"{rejected_count} rejected."
    )
    return clean_records
