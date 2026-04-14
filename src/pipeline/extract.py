"""
src/pipeline/extract.py — Extract step of the ETL pipeline
===========================================================
The Extract step is responsible for ONE thing: getting raw data
from the outside world and returning it in a consistent format.

In a larger system, extract.py might pull from:
  - Multiple APIs (Yahoo Finance + Alpha Vantage + Polygon.io)
  - Message queues (Kafka, RabbitMQ)
  - Files dropped in an S3 bucket
  - A database replica

For now, it wraps our Yahoo Finance fetcher. The benefit of this
indirection: if we want to swap the data source, we change this
file only. The transform and load steps never change.

WHAT "raw data" means here:
  A list of plain Python dicts, e.g.:
  [
    {"symbol": "AAPL",  "price": 175.50, "volume": 52000000, "fetched_at": "..."},
    {"symbol": "GOOGL", "price": 140.25, "volume": 18000000, "fetched_at": "..."},
  ]

The data is NOT validated here. It may contain None values, wrong
types, or missing keys. That is the transform step's job.
"""

import logging
from typing import Optional

from src.ingestion.fetcher import fetch_all_symbols

logger = logging.getLogger(__name__)


def extract(symbols: Optional[list[str]] = None) -> list[dict]:
    """
    Fetch raw stock price data for the configured symbols.

    Args:
        symbols: List of ticker symbols to fetch.
                 If None, uses STOCK_SYMBOLS from config (.env).

    Returns:
        List of raw price dicts. May be empty if all fetches fail.
        Data is NOT validated — pass to transform() next.
    """
    logger.info("EXTRACT: Starting data extraction...")

    raw_records = fetch_all_symbols(symbols)

    logger.info(f"EXTRACT: Retrieved {len(raw_records)} raw record(s).")
    return raw_records
