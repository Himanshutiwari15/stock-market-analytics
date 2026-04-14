"""
src/database/models.py — SQLAlchemy ORM table definitions
==========================================================
An ORM (Object-Relational Mapper) lets you work with database
tables as Python classes instead of writing raw SQL.

Instead of:
    INSERT INTO stock_prices (symbol, price, volume, fetched_at)
    VALUES ('AAPL', 175.50, 52000000, '2024-01-15 14:30:00+00');

You write:
    row = StockPrice(symbol="AAPL", price=175.50, volume=52000000)
    session.add(row)

The ORM translates Python objects to SQL automatically.

WHY use an ORM?
  - Type safety: Python catches type errors before they hit the database
  - Readability: Python code is easier to review than SQL strings
  - Portability: switching from PostgreSQL to SQLite (for tests) is trivial
  - Security: parameterised queries are generated automatically —
    no risk of SQL injection from string formatting

WHEN raw SQL is better:
  - Complex analytical queries (multi-table joins, window functions)
  - Bulk inserts of millions of rows (ORM overhead matters at scale)
  - Database-specific features (PostgreSQL JSONB, array operations)
  - We'll use raw SQL for some Grafana queries in Phase 6
"""

from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime, Index, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


# DeclarativeBase is the SQLAlchemy 2.0 way to define the base class.
# All model classes inherit from Base.
# Base keeps a registry of all models — used by create_all() to create tables.
class Base(DeclarativeBase):
    """Base class for all ORM models in this project."""
    pass


class StockPrice(Base):
    """
    ORM model for the stock_prices table.

    Mirrors the schema defined in docker/postgres/init.sql.
    Both must stay in sync — if you add a column here, add it there too.

    The Mapped[type] annotation is SQLAlchemy 2.0 style.
    It gives you proper type hints so your IDE knows what type
    each column holds (int, str, float, datetime, etc.).
    """

    __tablename__ = "stock_prices"

    # --- Columns ---

    # Auto-incrementing primary key. The database assigns this automatically.
    # You never set this yourself when inserting — just leave it out.
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Stock ticker symbol. Always stored as uppercase (enforced in the fetcher).
    # VARCHAR(20) in the database; str in Python.
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, index=True)

    # The closing price. Exact decimal arithmetic — never float.
    # Numeric(15, 4) → up to 15 digits total, 4 after the decimal point.
    # Python receives this as a Decimal object (from the decimal module).
    # We convert to float when needed (e.g. for Prometheus metrics).
    price: Mapped[float] = mapped_column(Numeric(15, 4), nullable=False)

    # Trading volume. BigInteger supports values up to ~9.2 quintillion.
    # Defaults to 0 when volume is not available (pre/after market).
    volume: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)

    # When this record was fetched from the API.
    # timezone=True → TIMESTAMPTZ in PostgreSQL (stores as UTC).
    # default= is called at insert time if not provided explicitly.
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # --- Constraints and indexes ---
    # We define these here so SQLAlchemy's create_all() can create them
    # in non-PostgreSQL databases (e.g. SQLite for testing).
    # They mirror what init.sql defines for the real PostgreSQL database.
    __table_args__ = (
        # Prevent duplicate rows: same symbol cannot appear twice
        # at the exact same timestamp. Enforces idempotent inserts.
        UniqueConstraint("symbol", "fetched_at", name="uq_stock_prices_symbol_time"),

        # Composite index for the most common query pattern:
        # "Get all AAPL prices in the last hour, newest first."
        Index("idx_stock_prices_symbol_time", "symbol", "fetched_at"),
    )

    def __repr__(self) -> str:
        """
        String representation for debugging.
        When you print(stock_price_object) in the Python REPL,
        this is what you see — much more useful than <StockPrice object>.

        We format price with :.4f so trailing zeros are preserved:
        245.80 shows as 245.8000 — not 245.8 (Python's default float repr).
        """
        return (
            f"<StockPrice("
            f"id={self.id}, "
            f"symbol='{self.symbol}', "
            f"price={float(self.price):.4f}, "
            f"fetched_at={self.fetched_at}"
            f")>"
        )

    def to_dict(self) -> dict:
        """
        Convert this ORM object to a plain Python dict.
        Useful for serialisation (logging, JSON responses, etc.)
        """
        return {
            "id": self.id,
            "symbol": self.symbol,
            "price": float(self.price),  # convert Decimal → float for JSON
            "volume": self.volume,
            "fetched_at": self.fetched_at.isoformat() if self.fetched_at else None,
        }
