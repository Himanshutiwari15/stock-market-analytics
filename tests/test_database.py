"""
tests/test_database.py — Unit tests for the database layer
===========================================================
These tests verify the model structure, constraints, and
connection logic WITHOUT requiring a real running database.

We use SQLite in-memory (:memory:) as a test database.
SQLite is a file-based database built into Python's standard
library — no installation, no Docker needed. It supports the
same SQL commands as PostgreSQL for basic CRUD operations.

WHY SQLite for unit tests?
  - Zero setup: no Docker, no credentials, no network
  - Runs in memory: each test starts with a clean empty database
  - Extremely fast: no disk I/O
  - Sufficient: we're testing OUR model logic, not PostgreSQL-specific features

The trade-off:
  - SQLite doesn't support every PostgreSQL feature (e.g. TIMESTAMPTZ,
    NUMERIC behaves slightly differently). For those, we write
    integration tests that run against a real PostgreSQL container.
    We'll add those in Phase 5 when Docker is fully wired up.
"""

from datetime import datetime, timezone, timedelta

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from src.database.models import Base, StockPrice


# -------------------------------------------------------
# Fixtures — shared setup for all tests in this file
# -------------------------------------------------------

@pytest.fixture
def db_engine():
    """
    Create a fresh SQLite in-memory database for each test.
    Base.metadata.create_all() reads our model definitions and
    creates the matching tables in the test database.
    After the test, the database is automatically destroyed.
    """
    # "sqlite:///:memory:" = in-memory SQLite (destroyed after use)
    engine = create_engine("sqlite:///:memory:")
    # Create all tables defined in our models
    Base.metadata.create_all(engine)
    yield engine
    # Teardown: drop everything (redundant for :memory: but explicit)
    Base.metadata.drop_all(engine)


@pytest.fixture
def db_session(db_engine):
    """
    Provide a database session connected to the test database.
    The session is rolled back after each test, ensuring tests
    are isolated from each other (no data leaks between tests).
    """
    SessionLocal = sessionmaker(bind=db_engine)
    session = SessionLocal()
    yield session
    session.rollback()
    session.close()


# -------------------------------------------------------
# Tests for StockPrice model structure
# -------------------------------------------------------

class TestStockPriceModel:
    """Tests that the StockPrice model is defined correctly."""

    def test_table_name_is_correct(self):
        """The ORM model must point to the right table in the database."""
        assert StockPrice.__tablename__ == "stock_prices"

    def test_table_has_all_required_columns(self, db_engine):
        """
        All columns defined in the model must exist in the database.
        This test would catch a typo in a column name, for example.
        """
        inspector = inspect(db_engine)
        columns = {col["name"] for col in inspector.get_columns("stock_prices")}

        assert "id" in columns
        assert "symbol" in columns
        assert "price" in columns
        assert "volume" in columns
        assert "fetched_at" in columns

    def test_can_insert_and_retrieve_a_row(self, db_session):
        """
        Happy path: create a StockPrice, save it, read it back.
        Verifies the full round-trip through the ORM.
        """
        now = datetime.now(timezone.utc)

        row = StockPrice(
            symbol="AAPL",
            price=175.50,
            volume=52_000_000,
            fetched_at=now,
        )
        db_session.add(row)
        db_session.commit()

        # Query it back
        retrieved = db_session.query(StockPrice).filter_by(symbol="AAPL").first()

        assert retrieved is not None
        assert retrieved.symbol == "AAPL"
        assert float(retrieved.price) == 175.50
        assert retrieved.volume == 52_000_000

    def test_id_is_auto_assigned(self, db_session):
        """
        The id column must be populated automatically by the database.
        We should never need to set it manually.
        """
        row = StockPrice(symbol="GOOGL", price=140.25, volume=18_000_000)
        db_session.add(row)
        db_session.commit()

        assert row.id is not None
        assert isinstance(row.id, int)
        assert row.id > 0

    def test_default_volume_is_zero(self, db_session):
        """
        Volume has a default of 0. Inserting without providing volume
        should store 0, not None.
        """
        row = StockPrice(
            symbol="MSFT",
            price=370.87,
            fetched_at=datetime.now(timezone.utc),
        )
        db_session.add(row)
        db_session.commit()

        retrieved = db_session.query(StockPrice).filter_by(symbol="MSFT").first()
        assert retrieved.volume == 0

    def test_repr_contains_key_info(self):
        """
        The __repr__ method should include symbol, price, and id
        so that print(row) gives useful information during debugging.
        """
        row = StockPrice(id=1, symbol="TSLA", price=245.80)
        representation = repr(row)

        assert "TSLA" in representation
        assert "245.80" in representation
        assert "1" in representation

    def test_to_dict_returns_correct_structure(self, db_session):
        """
        to_dict() must return a plain dict with all fields.
        This is used for logging and JSON serialisation.
        """
        now = datetime.now(timezone.utc)
        row = StockPrice(symbol="AAPL", price=175.50, volume=52_000_000, fetched_at=now)
        db_session.add(row)
        db_session.commit()

        result = row.to_dict()

        assert result["symbol"] == "AAPL"
        assert result["price"] == 175.50
        assert result["volume"] == 52_000_000
        assert isinstance(result["price"], float)   # must be float, not Decimal
        assert isinstance(result["fetched_at"], str)  # must be ISO string

    def test_multiple_symbols_can_coexist(self, db_session):
        """Different symbols can have rows at the same timestamp."""
        now = datetime.now(timezone.utc)

        db_session.add_all([
            StockPrice(symbol="AAPL",  price=175.50, fetched_at=now),
            StockPrice(symbol="GOOGL", price=140.25, fetched_at=now),
            StockPrice(symbol="MSFT",  price=370.87, fetched_at=now),
        ])
        db_session.commit()

        count = db_session.query(StockPrice).count()
        assert count == 3

    def test_can_filter_by_symbol(self, db_session):
        """Querying by symbol returns only rows for that symbol."""
        now = datetime.now(timezone.utc)

        # Two AAPL rows must have DIFFERENT timestamps — the unique constraint
        # on (symbol, fetched_at) correctly rejects identical symbol+time pairs.
        # This mirrors reality: in production, each pipeline run happens at a
        # different time, so the same symbol never appears twice at the same moment.
        db_session.add_all([
            StockPrice(symbol="AAPL",  price=175.50, fetched_at=now),
            StockPrice(symbol="AAPL",  price=176.00, fetched_at=now + timedelta(minutes=1)),
            StockPrice(symbol="GOOGL", price=140.25, fetched_at=now),
        ])
        db_session.commit()

        aapl_rows = db_session.query(StockPrice).filter_by(symbol="AAPL").all()
        assert len(aapl_rows) == 2
        assert all(r.symbol == "AAPL" for r in aapl_rows)
