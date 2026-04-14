-- =============================================================
-- docker/postgres/init.sql — Database Schema
-- =============================================================
-- This file runs automatically the FIRST TIME the PostgreSQL
-- container starts (Docker mounts it into the container's
-- /docker-entrypoint-initdb.d/ directory and Postgres executes
-- every .sql file it finds there on first boot).
--
-- If you delete the Docker volume and restart, this runs again.
-- If the volume already exists, this file is NOT re-run.
-- This means schema changes must be handled via migrations
-- (we will introduce those properly in a later phase).
--
-- DESIGN DECISIONS:
--   - NUMERIC(15,4) for price — exact decimal, never float
--   - BIGINT for volume     — can exceed 2 billion on high-cap stocks
--   - TIMESTAMPTZ           — timestamp WITH timezone, always stored as UTC
--   - Unique constraint     — prevents duplicate rows for same symbol+time
--   - Composite index       — speeds up "get AAPL prices in the last hour" queries
-- =============================================================


-- -------------------------------------------------------
-- 1. Create the main stock prices table
-- -------------------------------------------------------
CREATE TABLE IF NOT EXISTS stock_prices (
    -- Auto-incrementing primary key.
    -- Every row gets a unique ID automatically.
    id          SERIAL PRIMARY KEY,

    -- Stock ticker symbol, e.g. 'AAPL', 'GOOGL'.
    -- VARCHAR(20) is generous — longest tickers are ~5 chars.
    -- NOT NULL: we never store a price without knowing what stock it is.
    symbol      VARCHAR(20)     NOT NULL,

    -- The closing price for this data point.
    -- NUMERIC(15, 4): up to 15 significant digits, 4 after decimal.
    -- Examples: 175.5000 | 43251.7800 (BTC) | 0.0012 (penny crypto)
    -- WHY NOT FLOAT: floats have binary rounding errors.
    --   0.1 + 0.2 = 0.30000000000000004 in float arithmetic.
    --   NUMERIC is exact. For financial data, always use NUMERIC.
    price       NUMERIC(15, 4)  NOT NULL,

    -- Trading volume (number of shares/units traded).
    -- BIGINT supports up to 9.2 quintillion — safe for any volume.
    -- DEFAULT 0 because volume is not always available (e.g. pre/post market).
    volume      BIGINT          NOT NULL DEFAULT 0,

    -- When this price was fetched from the API.
    -- TIMESTAMPTZ = timestamp WITH time zone.
    -- PostgreSQL stores it as UTC internally, regardless of server timezone.
    -- Always use TIMESTAMPTZ, never TIMESTAMP — timezone-naive timestamps
    -- cause subtle bugs when your server or team spans multiple timezones.
    fetched_at  TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);


-- -------------------------------------------------------
-- 2. Unique constraint — prevent duplicate rows
-- -------------------------------------------------------
-- We should never have two rows for the same symbol at the exact same time.
-- This constraint makes the database enforce that rule automatically.
-- Without this, a bug that runs the pipeline twice would silently double
-- all your data — and you might not notice for days.
--
-- ON CONFLICT DO NOTHING (used in the Python load step) + this constraint
-- = truly idempotent inserts. Safe to run the pipeline as many times as you want.
ALTER TABLE stock_prices
    ADD CONSTRAINT uq_stock_prices_symbol_time
    UNIQUE (symbol, fetched_at);


-- -------------------------------------------------------
-- 3. Composite index — speed up time-series queries
-- -------------------------------------------------------
-- The most common query pattern in a stock analytics platform:
--   "Give me all prices for AAPL in the last 24 hours, newest first."
--   SELECT * FROM stock_prices
--   WHERE symbol = 'AAPL'
--   ORDER BY fetched_at DESC
--   LIMIT 100;
--
-- Without an index, PostgreSQL scans every row in the table (slow).
-- With this index, it jumps directly to AAPL rows sorted by time (fast).
-- The "IF NOT EXISTS" means re-running this script is safe.
CREATE INDEX IF NOT EXISTS idx_stock_prices_symbol_time
    ON stock_prices (symbol, fetched_at DESC);


-- -------------------------------------------------------
-- 4. Seed data — useful for testing the Grafana dashboard
-- -------------------------------------------------------
-- These rows mean the dashboard has something to show immediately,
-- even before the ETL pipeline has run. They will be overwritten
-- by real data once the pipeline starts.
INSERT INTO stock_prices (symbol, price, volume, fetched_at) VALUES
    ('AAPL',  175.5000, 52000000, NOW() - INTERVAL '5 minutes'),
    ('GOOGL', 140.2500, 18000000, NOW() - INTERVAL '5 minutes'),
    ('MSFT',  370.1000, 22000000, NOW() - INTERVAL '5 minutes'),
    ('TSLA',  245.8000, 90000000, NOW() - INTERVAL '5 minutes')
ON CONFLICT (symbol, fetched_at) DO NOTHING;


-- -------------------------------------------------------
-- 5. Helpful view for Grafana queries
-- -------------------------------------------------------
-- A VIEW is a saved SQL query that behaves like a table.
-- Grafana can query this directly for its "latest prices" panel.
-- We use DISTINCT ON to get only the most recent row per symbol.
CREATE OR REPLACE VIEW latest_stock_prices AS
SELECT DISTINCT ON (symbol)
    id,
    symbol,
    price,
    volume,
    fetched_at
FROM stock_prices
ORDER BY symbol, fetched_at DESC;
