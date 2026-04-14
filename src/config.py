"""
src/config.py — Central configuration loader
=============================================
All configuration values for the application live here.
Every other module imports from this file instead of
calling os.environ directly.

WHY centralise configuration?
  - One place to look for every config value
  - If an environment variable is missing, you get a clear,
    helpful error immediately — not a cryptic KeyError deep
    in your code when it's too late
  - Easy to see exactly what the app needs to run (audit the
    .env.example file alongside this one)
  - Simple to change a variable name: update it here and the
    rest of the codebase is unaffected

HOW it works:
  1. load_dotenv() reads your .env file into os.environ
  2. We read each variable with os.environ.get()
  3. Values are cast to the correct Python type (int, float, list)
  4. Module-level constants are exported for use everywhere

USAGE in other modules:
  from src.config import STOCK_SYMBOLS, FETCH_INTERVAL_SECONDS
"""

import os
import logging

from dotenv import load_dotenv

# Load the .env file into os.environ.
# - If .env exists (local dev): variables are loaded from it.
# - If .env doesn't exist (CI/production): environment variables
#   are expected to already be set by the platform. load_dotenv
#   does nothing harmful if the file is absent — it just skips.
load_dotenv()


# -------------------------------------------------------
# Internal helpers
# -------------------------------------------------------

def _get_required(key: str) -> str:
    """
    Get a required environment variable.
    Raises a clear EnvironmentError if it is not set.
    Use this for secrets that have no sensible default (e.g. DB password).
    """
    value = os.environ.get(key)
    if not value:
        raise EnvironmentError(
            f"\n\nMissing required environment variable: '{key}'\n"
            f"Fix: Copy .env.example to .env and set a value for {key}\n"
        )
    return value


def _get_optional(key: str, default: str) -> str:
    """
    Get an optional environment variable with a fallback default.
    Use this for settings that have a sensible value even without .env.
    """
    return os.environ.get(key, default)


# -------------------------------------------------------
# Stock data settings
# -------------------------------------------------------

# STOCK_SYMBOLS: the list of tickers to track.
# We split a comma-separated string and strip any spaces.
# e.g. "AAPL, GOOGL, MSFT" → ["AAPL", "GOOGL", "MSFT"]
STOCK_SYMBOLS: list[str] = [
    s.strip().upper()
    for s in _get_optional("STOCK_SYMBOLS", "AAPL,GOOGL,MSFT,TSLA").split(",")
    if s.strip()  # ignore empty strings if someone puts a trailing comma
]

# How often (in seconds) to run the ETL pipeline.
FETCH_INTERVAL_SECONDS: int = int(
    _get_optional("FETCH_INTERVAL_SECONDS", "60")
)

# -------------------------------------------------------
# PostgreSQL database settings
# -------------------------------------------------------

POSTGRES_HOST: str = _get_optional("POSTGRES_HOST", "localhost")
POSTGRES_PORT: int = int(_get_optional("POSTGRES_PORT", "5432"))
POSTGRES_DB: str = _get_optional("POSTGRES_DB", "stockmarket")
POSTGRES_USER: str = _get_optional("POSTGRES_USER", "stockuser")

# POSTGRES_PASSWORD has a default of empty string here so that
# Phase 2 (ingestion) works without a database being configured yet.
# In Phase 3 (database setup), we will make this required.
POSTGRES_PASSWORD: str = _get_optional("POSTGRES_PASSWORD", "")

# Convenience: full connection URL used by SQLAlchemy
# Format: postgresql://user:password@host:port/database
POSTGRES_URL: str = (
    f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}"
    f"@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
)

# -------------------------------------------------------
# Email alert settings (Gmail SMTP)
# -------------------------------------------------------

SMTP_HOST: str = _get_optional("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT: int = int(_get_optional("SMTP_PORT", "587"))
SMTP_USER: str = _get_optional("SMTP_USER", "")
SMTP_PASSWORD: str = _get_optional("SMTP_PASSWORD", "")
ALERT_RECIPIENT: str = _get_optional("ALERT_RECIPIENT", "")

# -------------------------------------------------------
# Anomaly detection settings
# -------------------------------------------------------

# Z-SCORE APPROACH (Phase 11)
# ---------------------------
# A Z-score measures how many standard deviations a value is
# from the mean of a baseline dataset.
#
# Formula:  z = (current_price - mean) / std_dev
#
# z = 0   → exactly average
# z = 1   → one standard deviation above average (~84th percentile)
# z = 2   → two std devs above (~97.7th percentile)
# z = 2.5 → our threshold: unusually extreme, worth alerting on
# z = -2.5 → same on the downside (price crash)
#
# Why 2.5? In a normal distribution, only ~1.2% of values exceed
# this threshold — so it keeps false positives low while catching
# genuine spikes and crashes.

# Number of days of historical price data to use as the baseline.
# We compute mean + std dev over this window, then compare the
# latest price against those statistics.
ANOMALY_LOOKBACK_DAYS: int = int(
    _get_optional("ANOMALY_LOOKBACK_DAYS", "20")
)

# Alert if |z-score| exceeds this value. Default: 2.5
ANOMALY_Z_SCORE_THRESHOLD: float = float(
    _get_optional("ANOMALY_Z_SCORE_THRESHOLD", "2.5")
)

# -------------------------------------------------------
# Application settings
# -------------------------------------------------------

LOG_LEVEL: str = _get_optional("LOG_LEVEL", "INFO")

# -------------------------------------------------------
# Logging setup
# -------------------------------------------------------
# We configure logging here so that any module that imports
# from config.py automatically gets a consistent log format.
# Every log line shows: time | level | module name | message
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
