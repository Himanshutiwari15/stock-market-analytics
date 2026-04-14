# tests/conftest.py
# =============================================================
# conftest.py is a special pytest file.
# =============================================================
# Fixtures defined here are automatically available to ALL
# test files in the tests/ directory — no import needed.
#
# Use conftest.py for:
#   - Shared test fixtures (e.g., a mock database connection)
#   - Common test data (e.g., sample stock price DataFrames)
#   - Test configuration (e.g., environment variable overrides)
#
# We will populate this file as we add tests in each phase.
# =============================================================

import pytest


# Example of a fixture — this one provides sample stock data
# that multiple test files can use. We'll add real fixtures
# starting in Phase 2.
@pytest.fixture
def sample_stock_data():
    """
    Provides a minimal dict of stock data for testing.
    This avoids making real API calls in unit tests.
    Real API calls are slow, unreliable in CI, and unnecessary
    when we just want to test our *processing* logic.
    """
    return {
        "symbol": "AAPL",
        "price": 175.50,
        "volume": 52_000_000,
        "timestamp": "2024-01-15 14:30:00",
    }
