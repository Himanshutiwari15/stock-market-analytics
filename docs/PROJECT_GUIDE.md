# Real-Time Stock Market Analytics Platform — Complete Project Guide

**Purpose of this document:** A self-study reference that explains every concept, every tool, every design decision, and every piece of code in this project. Read this to truly understand what you built, why it works the way it does, and how to explain it confidently in interviews.

---

## Table of Contents

1. [What the Project Does — The Big Picture](#1-what-the-project-does)
2. [The Full Data Flow — Step by Step](#2-the-full-data-flow)
3. [Python Application Code](#3-python-application-code)
   - [config.py — The Configuration Hub](#31-configpy)
   - [The Fetcher — Getting Data from Yahoo Finance](#32-the-fetcher)
   - [The ETL Pipeline — Extract, Transform, Load](#33-the-etl-pipeline)
   - [The Database Layer — PostgreSQL + SQLAlchemy](#34-the-database-layer)
   - [Prometheus Metrics — Instrumenting the Pipeline](#35-prometheus-metrics)
   - [Anomaly Detector — Z-Score Statistics](#36-anomaly-detector)
   - [Email Alerter — Gmail SMTP](#37-email-alerter)
4. [Docker and Docker Compose](#4-docker-and-docker-compose)
5. [PostgreSQL — The Database](#5-postgresql)
6. [Grafana — Dashboards](#6-grafana)
7. [Prometheus — Metrics and Monitoring](#7-prometheus)
8. [GitHub Actions — CI/CD Pipeline](#8-github-actions)
9. [Security Scanning — Bandit and pip-audit](#9-security-scanning)
10. [Terraform — Infrastructure as Code](#10-terraform)
11. [Testing Strategy](#11-testing-strategy)
12. [Key Concepts Glossary](#12-key-concepts-glossary)
13. [Interview Preparation](#13-interview-preparation)

---

## 1. What the Project Does

This platform continuously collects live stock prices, processes them, stores them, and watches for unusual movements. Here is every capability in plain English:

| Capability | What happens | File responsible |
|------------|-------------|-----------------|
| Data ingestion | Every 60 seconds, Python asks Yahoo Finance for the latest price of AAPL, GOOGL, MSFT, TSLA | `src/ingestion/fetcher.py` |
| Data cleaning | Each price is validated (is it positive? is the symbol valid?) and normalised | `src/pipeline/transform.py` |
| Storage | Clean prices are written to PostgreSQL with a timestamp | `src/pipeline/load.py` |
| Visualisation | Grafana reads the database and draws live price charts | `monitoring/grafana/` |
| Pipeline monitoring | Prometheus records how many rows were inserted, how many failed, how long each run took | `src/monitoring/metrics.py` |
| Anomaly detection | Every 60 seconds, a separate process computes Z-scores and flags unusual prices | `src/alerts/anomaly_detector.py` |
| Email alerting | If an anomaly is found, an HTML email is sent via Gmail | `src/alerts/email_alerter.py` |
| CI/CD | Every git push runs linting, tests, and two security scans automatically | `.github/workflows/ci.yml` |
| Cloud infrastructure | Terraform defines EC2 + RDS + VPC on AWS (ready to apply) | `infrastructure/` |

---

## 2. The Full Data Flow

Understanding the sequence of events from start to finish is the most important mental model for this project.

```
EVERY 60 SECONDS:

Step 1 — FETCH
  Python calls yfinance.Ticker("AAPL").history(period="1d", interval="1m")
  Yahoo Finance returns a pandas DataFrame with OHLCV columns
  fetcher.py extracts the latest row and returns:
    { "symbol": "AAPL", "price": 189.4200, "volume": 5234100, "timestamp": ... }

Step 2 — EXTRACT
  pipeline/extract.py calls fetch_all_symbols(["AAPL","GOOGL","MSFT","TSLA"])
  Returns a list of 4 raw dicts (one per symbol)

Step 3 — TRANSFORM
  pipeline/transform.py validates each dict:
    - symbol must be non-empty string, max 20 chars
    - price must be positive number
    - volume must be non-negative integer
  Converts each valid dict to a StockPrice ORM object
  Drops invalid records (logs a warning for each)

Step 4 — LOAD
  pipeline/load.py opens a database session
  Tries to INSERT each StockPrice object
  If the (symbol, fetched_at) combination already exists → skip (idempotent)
  Tracks counts: inserted / skipped / failed
  Updates Prometheus metrics gauges

Step 5 — PROMETHEUS RECORDS
  After each run, metrics.py updates:
    pipeline_runs_total (counter: how many times pipeline ran)
    pipeline_rows_inserted_total (counter: cumulative inserts)
    pipeline_last_run_timestamp (gauge: when did it last run)
    pipeline_duration_seconds (gauge: how long the last run took)
  These are exposed at http://localhost:8000/metrics

Step 6 — PROMETHEUS SCRAPES
  Every 15 seconds, the Prometheus container sends an HTTP GET to
  http://app:8000/metrics and stores the values in its time-series database

Step 7 — GRAFANA READS
  Grafana has two data sources:
    1. PostgreSQL (reads stock_prices table directly for price charts)
    2. Prometheus (reads scraped metrics for the ops dashboard)
  Dashboards auto-refresh every 30 seconds

ANOMALY DETECTION (runs in parallel, every 60 seconds):

Step A — QUERY HISTORY
  anomaly_detector.py queries PostgreSQL:
  "Give me all prices for AAPL in the last 20 days, ordered by time"

Step B — COMPUTE Z-SCORE
  Takes all rows except the most recent as the "baseline"
  Computes: mean = average of baseline prices
            stdev = standard deviation of baseline prices
  Computes: z = (latest_price - mean) / stdev

Step C — THRESHOLD CHECK
  If |z| > 2.5: flag as anomaly
  If stdev == 0: skip (flat price, can't compute)
  If fewer than 3 rows: skip (not enough data)

Step D — EMAIL (if anomaly found)
  email_alerter.py connects to smtp.gmail.com:587
  Upgrades to TLS with STARTTLS
  Logs in with App Password
  Sends an HTML email with a table of all flagged symbols
```

---

## 3. Python Application Code

### 3.1 config.py

**File:** `src/config.py`

**What it does:** Acts as the single source of truth for all configuration. Every other module imports from here instead of calling `os.environ` directly.

**Why this pattern matters:**

If you scatter `os.environ.get("POSTGRES_HOST")` calls across 10 files, and you need to rename that variable, you have to find and update 10 places. With a central config file, you update one line. You also get a single place to see exactly what environment variables the app needs — great for onboarding and debugging.

**Key function — `_get_required(key)`:**
```python
def _get_required(key: str) -> str:
    value = os.environ.get(key)
    if not value:
        raise EnvironmentError(f"Missing required environment variable: '{key}'")
    return value
```
This fails immediately with a clear message if a secret is missing. Without it, the app might run for minutes before crashing with a cryptic `None` error deep in the database layer.

**Type casting:**
```python
POSTGRES_PORT: int = int(_get_optional("POSTGRES_PORT", "5432"))
```
`os.environ` always returns strings. Casting to `int` here means the rest of the code never has to worry about type conversion — it always gets an `int`.

**The ANOMALY_Z_SCORE_THRESHOLD setting:**
```python
ANOMALY_Z_SCORE_THRESHOLD: float = float(
    _get_optional("ANOMALY_Z_SCORE_THRESHOLD", "2.5")
)
```
Default 2.5 — this means "only alert if the price is more than 2.5 standard deviations from recent average." In a normal distribution, only ~1.2% of values exceed ±2.5σ. You can lower this in `.env` during testing.

---

### 3.2 The Fetcher

**File:** `src/ingestion/fetcher.py`

**What it does:** Uses the `yfinance` library to fetch the latest price for a stock symbol.

**Why yfinance?**
- Free — no API key, no rate limit registration
- Real, live data — not simulated
- Returns clean pandas DataFrames
- Widely used in the Python finance community

**The key call:**
```python
ticker = yfinance.Ticker(symbol)
hist = ticker.history(period="1d", interval="1m")
```
- `period="1d"` — give me today's data
- `interval="1m"` — in 1-minute candles
- The last row of `hist` is the most recent price

**What a "candle" is:**
Each row in the DataFrame represents one minute of trading. It has:
- `Open` — price at the start of that minute
- `High` — highest price during that minute
- `Low` — lowest price during that minute
- `Close` — price at the end of that minute (this is what we store)
- `Volume` — how many shares traded that minute

**Why `Close` and not `Open`?**
Close is the conventional "price" for a period. It's what you see on stock tickers. Open is where the period started, Close is where it ended.

**Defensive programming in the fetcher:**
```python
if hist.empty:
    return None   # Yahoo Finance returned no data

latest_price = float(hist["Close"].iloc[-1])
if latest_price <= 0:
    return None   # Invalid price
```
Without these guards, a downstream function receiving `None` or `0.0` as a price would silently store bad data. Fail early, fail loud.

---

### 3.3 The ETL Pipeline

**File:** `src/pipeline/extract.py`, `transform.py`, `load.py`, `scheduler.py`

**What is ETL?**
ETL stands for **Extract, Transform, Load** — the standard pattern for data pipelines:
- **Extract:** Pull raw data from the source (Yahoo Finance)
- **Transform:** Clean, validate, reshape the data
- **Load:** Write the clean data to the destination (PostgreSQL)

This separation of concerns means you can change how you fetch data (swap Yahoo Finance for Bloomberg) without touching the transform or load logic.

**Extract (`extract.py`):**
Simply calls `fetch_all_symbols()` from the fetcher. Returns a list of raw dicts. No business logic here — extraction is just retrieval.

**Transform (`transform.py`):**

The validation function checks every field:
```python
def validate_record(record: dict) -> bool:
    symbol = record.get("symbol", "")
    if not symbol or not isinstance(symbol, str):
        return False
    if len(symbol) > 20:
        return False

    price = record.get("price")
    try:
        price_float = float(price)
    except (TypeError, ValueError):
        return False
    if price_float <= 0 or price_float > 1_000_000:
        return False

    volume = record.get("volume", 0)
    if int(volume) < 0:
        return False

    return True
```
Why validate? Data from external APIs can be wrong. Yahoo Finance occasionally returns `0` prices during market close or API outages. Storing a `$0` price as if it were real would corrupt your charts and trigger false anomaly alerts.

**Load (`load.py`):**

The idempotent upsert pattern:
```python
try:
    session.add(stock_price_obj)
    session.flush()  # sends the INSERT without committing
    inserted += 1
except IntegrityError:
    session.rollback()
    skipped += 1    # (symbol, fetched_at) already exists — that's fine
```
The `UniqueConstraint("symbol", "fetched_at")` on the database table means inserting the same price twice will raise an `IntegrityError`. We catch it and skip rather than crash. This makes the pipeline **idempotent** — safe to run multiple times with the same data.

**Scheduler (`scheduler.py`):**
Uses `APScheduler` to run `run_once()` every `FETCH_INTERVAL_SECONDS`:
```python
scheduler = BlockingScheduler()
scheduler.add_job(run_once, "interval", seconds=FETCH_INTERVAL_SECONDS)
scheduler.start()
```
APScheduler handles the timing loop. `BlockingScheduler` means the Python process blocks here (stays alive) until you stop it — correct for a long-running service.

---

### 3.4 The Database Layer

**File:** `src/database/models.py`, `src/database/connection.py`

**What is SQLAlchemy?**
SQLAlchemy is a Python library that maps Python classes to database tables. Instead of writing raw SQL strings, you work with Python objects. It generates the SQL for you.

**The StockPrice model:**
```python
class StockPrice(Base):
    __tablename__ = "stock_prices"

    id:         Mapped[int]      = mapped_column(Integer, primary_key=True)
    symbol:     Mapped[str]      = mapped_column(String(20), nullable=False, index=True)
    price:      Mapped[float]    = mapped_column(Numeric(15, 4), nullable=False)
    volume:     Mapped[int]      = mapped_column(BigInteger, nullable=False, default=0)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
```

**Why `Numeric(15, 4)` for price, not `Float`?**
`Float` is a binary floating-point type — it cannot represent all decimal values exactly. `0.1 + 0.2` in binary float is `0.30000000000000004`. For financial data, this matters. `Numeric(15, 4)` stores exact decimal values (up to 15 digits, 4 after the decimal point). PostgreSQL calls this `DECIMAL`.

**Why `DateTime(timezone=True)`?**
Stores timestamps as `TIMESTAMPTZ` in PostgreSQL — always UTC. If you stored without timezone, you'd have an ambiguous timestamp: is `14:30:00` New York time? London time? UTC? With timezone=True, it's always UTC and you never have this problem.

**Why `BigInteger` for volume?**
Apple's daily trading volume is often over 50 million shares. `Integer` in PostgreSQL maxes out at ~2.1 billion, which sounds fine — but individual minute-candle volumes during earnings can be very high. `BigInteger` (up to ~9.2 quintillion) is safe.

**Connection pooling (`connection.py`):**
```python
_engine = create_engine(
    POSTGRES_URL,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)
```
Opening a database connection is expensive: TCP handshake + authentication + session setup. A connection pool opens N connections at startup and keeps them ready. When your code needs a connection, it borrows one from the pool and returns it when done.

`pool_pre_ping=True` — before handing a connection to your code, the pool sends `SELECT 1` to test it. If the database restarted and the connection is stale, the pool reconnects transparently. Without this, you'd get "connection closed" errors after idle periods.

**The context manager pattern:**
```python
@contextmanager
def get_session() -> Generator[Session, None, None]:
    session = _get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
```
The `with get_session() as session:` pattern guarantees that the session is always closed, whether the code succeeded or raised an exception. Without this, a crash inside the `with` block would leave the connection open and eventually exhaust the pool.

---

### 3.5 Prometheus Metrics

**File:** `src/monitoring/metrics.py`

**What is Prometheus?**
Prometheus is a monitoring system that works by "scraping" — periodically sending HTTP GET requests to your app at `/metrics` and collecting the current metric values. It stores these values over time in its own database (TSDB), which Grafana queries for charts.

**The two metric types we use:**

**Counter:** A number that only goes up (like an odometer).
```python
pipeline_runs_total = Counter(
    "pipeline_runs_total",
    "Total number of pipeline runs"
)
```
Used for: total rows inserted, total errors, total runs. You never reset a counter — if the process restarts, it starts from 0 again, but Prometheus tracks the `rate()` (how fast it increases) which is what you actually want to chart.

**Gauge:** A number that goes up and down (like a speedometer).
```python
pipeline_last_run_timestamp = Gauge(
    "pipeline_last_run_timestamp_seconds",
    "Unix timestamp of the last successful pipeline run"
)
```
Used for: current price, duration of last run, timestamp of last run. You `set()` a gauge to a value, unlike a counter which you `inc()`.

**The `/metrics` endpoint:**
```python
start_http_server(8000)
```
This starts a plain HTTP server on port 8000. When Prometheus calls `http://app:8000/metrics`, it gets back text like:
```
pipeline_runs_total 42
pipeline_rows_inserted_total 168
pipeline_last_run_duration_seconds 0.234
```
Prometheus parses this format (called "Prometheus exposition format") and stores each value with a timestamp.

---

### 3.6 Anomaly Detector

**File:** `src/alerts/anomaly_detector.py`

**The problem it solves:**
A 3% price move on Tesla (which routinely moves 5-10% per day) is not alarming. A 3% move on Apple (which typically moves 0.5-1% per day) is extraordinary. A fixed percent threshold would either spam Tesla alerts or miss Apple events.

**The Z-score solution:**
The Z-score measures how many standard deviations a value is from the mean of a reference dataset. It's self-normalising: it accounts for each stock's own volatility.

**The maths:**
```
z = (x - μ) / σ

where:
  x = the latest price we're evaluating
  μ = mean (average) of the baseline prices
  σ = standard deviation of the baseline prices
```

**Worked example:**
Apple's 20-day prices have mean = $189.00 and std dev = $1.50.
- Latest price $192.00 → z = (192 - 189) / 1.5 = **+2.0** — elevated but below threshold
- Latest price $195.00 → z = (195 - 189) / 1.5 = **+4.0** — anomaly! Email fires.
- Latest price $182.00 → z = (182 - 189) / 1.5 = **-4.67** — anomaly! Price crash.

**Why 2.5 as the threshold?**
In a normal distribution:
- 68% of values fall within ±1σ
- 95.4% fall within ±2σ
- 98.8% fall within ±2.5σ → only 1.2% exceed this (false positive rate)
- 99.7% fall within ±3σ

2.5 is a balance: aggressive enough to catch real anomalies, conservative enough to avoid spam.

**The Anomaly dataclass:**
```python
@dataclass
class Anomaly:
    symbol: str
    latest_price: float
    mean: float
    stdev: float
    z_score: float
    direction: str       # "spike" or "drop"
    detected_at: datetime
    sample_size: int
```
A `dataclass` is a Python class where you declare fields as class-level type-annotated attributes and Python automatically generates `__init__`, `__repr__`, and `__eq__`. Cleaner than a plain dict (attribute access, not string keys) and simpler than writing a full class manually.

**Edge cases handled:**
- `len(rows) < 3` → skip. Can't compute standard deviation of 1 value.
- `stdev == 0` → skip. All prices are identical — dividing by zero would crash.
- `reference_time` parameter → injected in tests so we can control "now".

**Dependency injection (the session parameter):**
The function accepts a `session` parameter instead of creating one internally:
```python
def detect_anomalies(session: Session, symbols: list[str], ...) -> list[Anomaly]:
```
This is dependency injection. The caller provides the dependency (the database session). Benefits:
- In production: `runner.py` creates the real session
- In tests: tests inject a mock session — no database needed
- Single Responsibility: the detector detects; it doesn't manage connections

---

### 3.7 Email Alerter

**File:** `src/alerts/email_alerter.py`

**How SMTP works:**
SMTP (Simple Mail Transfer Protocol) is the protocol for sending email. The sequence when our code runs:

```
1. Our code → TCP connect to smtp.gmail.com:587
2. Server  → "220 smtp.gmail.com ESMTP"
3. Our code → "EHLO" (hello, I want to send mail)
4. Server  → lists capabilities including "STARTTLS"
5. Our code → "STARTTLS" (please upgrade to encrypted)
6. Server  → "220 Go ahead"
7.           [TLS handshake — all traffic is now encrypted]
8. Our code → "AUTH LOGIN" + base64(username) + base64(app_password)
9. Server  → "235 Authentication successful"
10. Our code → "MAIL FROM:", "RCPT TO:", "DATA", [message], "."
11. Server  → "250 OK, message accepted"
12. Our code → "QUIT"
```

**Why port 587 and not 465?**
- Port 465 (SMTPS) — the entire connection is SSL/TLS from the start (older)
- Port 587 (SMTP with STARTTLS) — starts plain, then upgrades to TLS
- Port 587 is the modern standard recommended by email providers

**Why App Passwords and not your real password?**
Google's "less secure app" plain-password auth is disabled for most accounts. App Passwords are special tokens that:
- Only grant SMTP access (can't read email, can't change account settings)
- Can be revoked individually without changing your main password
- Are 16 characters, effectively unguessable

**The HTML email body:**
We send HTML rather than plain text so the email looks professional:
```python
msg = MIMEMultipart("alternative")
msg.attach(MIMEText(html_body, "html"))
```
`MIMEMultipart("alternative")` is the correct MIME type for HTML emails. "Alternative" means the message has multiple representations — HTML clients show the HTML version. If the client doesn't support HTML, it shows nothing (we don't provide a plain-text fallback, but this is fine for an internal alert system).

**Error handling:**
Three specific exception types are caught separately:
- `SMTPAuthenticationError` → wrong credentials — tell the user clearly
- `SMTPException` → other SMTP protocol errors
- `OSError` → network problems (connection refused, DNS failure)

Each logs a specific, actionable message instead of a generic "email failed."

---

## 4. Docker and Docker Compose

**What is Docker?**
Docker packages an application and all its dependencies into a "container" — a lightweight, isolated process that runs the same way on any machine.

**The analogy:** A container is like a shipping container for software. The container is a standard format that works on any ship (any computer), regardless of what's inside.

**What is a Docker image?**
An image is the blueprint — a read-only snapshot of a filesystem with your app, its dependencies, and configuration. A container is a running instance of an image.

**The Dockerfile (`docker/app/Dockerfile`):**
```dockerfile
FROM python:3.12-slim           # Start from official Python 3.12 image
WORKDIR /app                    # Set working directory
COPY requirements.txt .         # Copy deps first (Docker layer cache)
RUN pip install -r requirements.txt  # Install Python packages
COPY src/ ./src/                # Copy application code
CMD ["python", "-m", "src.pipeline.scheduler"]  # Default command
```

**Why copy `requirements.txt` before `src/`?**
Docker builds images in layers. If `requirements.txt` hasn't changed, Docker reuses the cached layer for `pip install` — saving 60+ seconds on rebuilds. If you copied the whole `src/` first and a single Python file changed, Docker would re-run `pip install` unnecessarily.

**Docker Compose (`docker-compose.yml`):**
Defines 5 services that work together:

| Service | Image | What it does |
|---------|-------|-------------|
| `postgres` | postgres:15-alpine | The database |
| `app` | Built from our Dockerfile | ETL pipeline + metrics endpoint |
| `alerts` | Same Dockerfile, different CMD | Anomaly detection loop |
| `grafana` | grafana/grafana:10.3.1 | Dashboards |
| `prometheus` | prom/prometheus:v2.49.1 | Metrics collector |

**Named volumes:**
```yaml
volumes:
  postgres_data:
    name: stock_postgres_data
```
Without a named volume, all data in the container disappears when you run `docker compose down`. Named volumes persist on your machine, surviving container restarts and rebuilds. They are only deleted with `docker compose down -v`.

**Health checks:**
```yaml
healthcheck:
  test: ["CMD-SHELL", "pg_isready -U stockuser -d stockmarket"]
  interval: 10s
  timeout: 5s
  retries: 5
```
Docker uses this to know when a service is genuinely "ready" (not just "started"). The `app` service has `depends_on: postgres: condition: service_healthy` — it won't start until PostgreSQL passes its health check. Without this, the app might try to connect while PostgreSQL is still initialising and crash.

**Docker networking:**
All services are on the same `stock_network`. Docker's internal DNS lets them find each other by service name:
- Inside Docker: `POSTGRES_HOST=postgres` (the service name)
- Outside Docker (your laptop): `POSTGRES_HOST=localhost` (port-forwarded to 5432)

This is why the `app` service hard-codes `POSTGRES_HOST: postgres` in docker-compose.yml, overriding whatever is in your `.env` file.

**Why pin image versions?**
`postgres:15-alpine` vs `postgres:latest`:
- `latest` means "whatever is newest today" — in 6 months, `latest` might be PostgreSQL 17 with breaking changes
- `15-alpine` means "PostgreSQL 15, always" — your stack works the same on any machine at any time

---

## 5. PostgreSQL

**What is PostgreSQL?**
An open-source relational database — one of the most widely-used in production systems. Data is stored in tables (like spreadsheets) with rows and columns. You query it with SQL.

**Our schema (`docker/postgres/init.sql`):**
```sql
CREATE TABLE IF NOT EXISTS stock_prices (
    id          SERIAL PRIMARY KEY,
    symbol      VARCHAR(20)   NOT NULL,
    price       NUMERIC(15,4) NOT NULL,
    volume      BIGINT        NOT NULL DEFAULT 0,
    fetched_at  TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_stock_prices_symbol_time UNIQUE (symbol, fetched_at)
);

CREATE INDEX idx_stock_prices_symbol_time ON stock_prices (symbol, fetched_at DESC);
```

**Why `SERIAL` for `id`?**
`SERIAL` is shorthand for "auto-incrementing integer." PostgreSQL manages the sequence — you never set `id` manually, it's assigned on insert. Guarantees uniqueness.

**Why the `UNIQUE (symbol, fetched_at)` constraint?**
Prevents the same price from being stored twice. If the pipeline crashes and restarts, it might try to insert prices it already inserted. The unique constraint rejects duplicates with an error (which the code catches and ignores). This is called **idempotency** — running the operation multiple times has the same result as running it once.

**Why the composite index `(symbol, fetched_at DESC)`?**
The most common query is: "Give me all AAPL prices in the last 24 hours, newest first."
```sql
SELECT * FROM stock_prices
WHERE symbol = 'AAPL'
ORDER BY fetched_at DESC
LIMIT 1440;
```
Without an index, PostgreSQL scans every row in the table. With the index, it jumps directly to AAPL's rows and reads them in order. This is the difference between O(n) and O(log n) performance.

**`TIMESTAMPTZ` — why timezone matters:**
`TIMESTAMP` stores a local time with no timezone information. `TIMESTAMPTZ` (timestamp with timezone) stores the moment in UTC and converts to the session timezone when reading. We always work in UTC, so there is no ambiguity across daylight-saving changes or different server locations.

---

## 6. Grafana

**What is Grafana?**
A web-based visualisation tool. You connect it to data sources (PostgreSQL, Prometheus, etc.) and build dashboards with charts, tables, and gauges.

**Provisioning as code:**
Instead of clicking through the Grafana UI to set up data sources and dashboards, we define them as YAML and JSON files that Grafana reads at startup. This is called "provisioning."

Benefits:
- Configuration is version-controlled (in git)
- Anyone who clones the repo gets the exact same dashboard immediately
- No clicking through UIs — reproducible setup

**Data source (`monitoring/grafana/provisioning/datasources/postgres.yml`):**
Tells Grafana how to connect to PostgreSQL. Grafana runs SQL queries against this to fetch chart data.

**Dashboard JSON (`monitoring/grafana/dashboards/stock_overview.json`):**
A JSON file that defines the entire dashboard — panel layouts, queries, colours, thresholds. Grafana loads this file at startup. When you modify a dashboard in the UI and export the JSON, you can commit the change to git.

**The Grafana + PostgreSQL pattern:**
Grafana runs the following type of query directly against your database:
```sql
SELECT
    fetched_at AS "time",
    price
FROM stock_prices
WHERE symbol = 'AAPL'
  AND fetched_at > NOW() - INTERVAL '1 hour'
ORDER BY fetched_at ASC;
```
Grafana expects a `time` column and a value column. It plots the values over time automatically.

---

## 7. Prometheus

**What is Prometheus?**
A monitoring system that collects numeric metrics from your applications. It works by "pulling" — periodically asking your app "what are your current metric values?" and recording the answer.

**Why pull instead of push?**
Push model (your app sends metrics to a server): if the metrics server goes down, metrics are lost. If the metrics server is slow, it backs up.
Pull model (Prometheus asks your app): Prometheus controls the rate. If an app dies, Prometheus just records "no data" — it doesn't lose history.

**The scrape configuration (`monitoring/prometheus/prometheus.yml`):**
```yaml
scrape_configs:
  - job_name: "stock-pipeline"
    static_configs:
      - targets: ["app:8000"]
    scrape_interval: 15s
```
Every 15 seconds, Prometheus sends `GET http://app:8000/metrics` and stores all the returned metrics.

**Metric types:**

**Counter** — monotonically increasing (never decreases):
```
pipeline_runs_total{} 42
```
Never use a counter for something that can go down (e.g. current price). Prometheus detects counter resets (process restart) and handles them correctly.

**Gauge** — can increase or decrease:
```
pipeline_last_run_duration_seconds{} 0.234
```
Use for current values: temperature, memory usage, last run duration.

**PromQL (Prometheus Query Language):**
You can query metrics in Grafana using PromQL:
- `pipeline_runs_total` — current value
- `rate(pipeline_runs_total[5m])` — runs per second over the last 5 minutes
- `increase(pipeline_rows_inserted_total[1h])` — how many rows inserted in the last hour

---

## 8. GitHub Actions

**What is GitHub Actions?**
A CI/CD (Continuous Integration / Continuous Deployment) platform built into GitHub. Every time you push code, it automatically runs a workflow — in our case, lint → test → security scan.

**CI = Continuous Integration:**
Continuously integrate (merge) developer changes and verify they don't break anything. The "verify" step runs automatically on every push.

**The workflow file (`.github/workflows/ci.yml`):**

```yaml
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
```
Triggers on every push to main and on every pull request targeting main.

**The steps — and why each runs in this order:**

1. **Checkout** — Downloads your repository onto the GitHub-hosted Ubuntu VM
2. **Set up Python** — Installs Python 3.12, caches pip packages
3. **Install dependencies** — `pip install -r requirements.txt`
4. **Lint (ruff)** — Checks code style. Runs first because it's fast (~2s). If the style check fails, there's no point running the 30-second test suite.
5. **Test (pytest)** — Runs 66 tests. All tests use mocks — no Docker, no network needed.
6. **Bandit** — Scans Python source code for security vulnerabilities
7. **pip-audit** — Scans installed packages for known CVEs

**Why tests don't need Docker in CI:**
- `test_fetcher.py` — mocks the yfinance API
- `test_database.py` — uses SQLite in-memory
- `test_pipeline.py` — mocks the SQLAlchemy session
- `test_anomaly_detector.py` — mocks the SQLAlchemy session
- `test_email_alerter.py` — mocks smtplib.SMTP

This is the right way to write tests: fast, isolated, no external dependencies. Tests that depend on a running database or API are **integration tests** and belong in a separate stage.

**The pip cache:**
```yaml
cache: "pip"
```
GitHub Actions caches pip's downloaded packages keyed on the hash of `requirements.txt`. First run: ~60 seconds. Subsequent runs (if requirements.txt unchanged): ~5 seconds. A huge speed improvement for CI.

---

## 9. Security Scanning

**Two complementary tools — not redundant:**

### Bandit — Static Application Security Testing (SAST)

Bandit reads your Python source code (without running it) and looks for patterns associated with security vulnerabilities.

**What it checks:**
- **Hardcoded passwords:** `password = "mypassword"` — flags as HIGH severity
- **SQL injection risk:** `f"SELECT * FROM t WHERE id={user_input}"` — flags immediately
- **Dangerous functions:** `eval()`, `exec()`, `pickle.loads()` — can execute arbitrary code
- **Weak cryptography:** Using `md5` or `sha1` for passwords — easily brute-forced
- **Insecure random:** `random.random()` for security tokens — use `secrets` module instead
- **Subprocess with shell:** `subprocess.run(cmd, shell=True)` — vulnerable to injection

**The `.bandit` configuration file:**
Some Bandit warnings are false positives for our code. The `.bandit` file tells Bandit to skip specific test IDs with a documented reason. This is transparent — anyone can read why we suppressed a warning.

### pip-audit — Software Composition Analysis (SCA)

pip-audit checks your installed packages against the **OSV (Open Source Vulnerabilities)** database — a database of published CVEs (Common Vulnerabilities and Exposures) for open-source packages.

**What it checks:**
- Is this version of `requests` vulnerable to CVE-2024-XXXXX?
- Is this version of `SQLAlchemy` known to have a security flaw?

**The distinction:**
- Bandit = what **you** wrote wrong
- pip-audit = what your **dependencies** got wrong

Both run on every `git push`. If a new CVE is published for one of our dependencies, the next CI run will fail — alerting you to update the package.

**Why pip-audit instead of Safety?**
Safety v3+ requires creating an account and obtaining an API key. pip-audit is maintained by the Python Packaging Authority (the same organisation that maintains pip itself), requires no authentication, and is free.

---

## 10. Terraform

**What is Terraform?**
Terraform is a tool that lets you describe cloud infrastructure in code files (`.tf`) and then create, update, or delete that infrastructure by running commands. This is called "Infrastructure as Code" (IaC).

**Why IaC instead of clicking in the AWS console?**

| Manual (clicking) | IaC (Terraform) |
|-------------------|----------------|
| Hard to reproduce | `terraform apply` creates identical infra every time |
| No history of changes | Changes tracked in git |
| Easy to make mistakes | Reviewed like code, with `terraform plan` preview |
| Can't be tested | CI can validate the Terraform syntax |
| Slow | Runs in minutes |

**The key commands:**
```bash
terraform init     # Download providers (AWS plugin)
terraform plan     # Preview what will be created/changed/deleted
terraform apply    # Actually create/change/delete infrastructure
terraform destroy  # Delete everything Terraform created
```

**`terraform plan` is critical:**
Always run `plan` before `apply`. It shows you exactly what will change — "will create 12 resources, will modify 0, will destroy 0" — before anything happens. Never run `apply` blindly.

**Our AWS architecture:**

```
VPC (10.0.0.0/16) — your private network in AWS
│
├── Public Subnet  10.0.1.0/24  (AZ us-east-1a)
│   └── EC2 t2.micro — the app server
│       - Amazon Linux 2023
│       - Docker pre-installed (user_data bootstrap script)
│       - Security group: SSH from your IP only, ports 8000/3000/9090 open
│
├── Public Subnet  10.0.2.0/24  (AZ us-east-1b)  [second AZ, for resilience]
│
├── Private Subnet 10.0.101.0/24  (AZ us-east-1a)
│   └── RDS db.t3.micro — PostgreSQL 15
│       - Not publicly accessible (private subnet)
│       - Only the EC2 security group can connect on port 5432
│       - Encrypted at rest
│       - 7-day automated backups
│
└── Private Subnet 10.0.102.0/24  (AZ us-east-1b)  [required by AWS for RDS]
```

**Why public subnets for EC2 and private for RDS?**
EC2 needs a public IP so you can SSH in and so users can access the app. RDS never needs to be reached from the internet — only the app server needs to connect to it. Putting RDS in a private subnet means even if someone found the endpoint address, they cannot connect to it from outside the VPC.

**Terraform modules:**
We split infrastructure into modules — reusable blocks, like Python functions:
- `modules/ec2/` — takes VPC ID, subnet ID, key pair name → creates EC2 + security group → outputs public IP
- `modules/rds/` — takes VPC ID, subnet IDs, EC2 SG ID → creates RDS + subnet group → outputs endpoint

The root `main.tf` calls both modules, passing outputs from one to the other (e.g. EC2 security group ID → RDS security group ingress rule).

**Sensitive variables in Terraform:**
```hcl
variable "db_password" {
  type      = string
  sensitive = true  # Terraform never prints this in plan/apply output
}
```
Supply via environment variable: `export TF_VAR_db_password="your-password"` — it never appears in any file.

---

## 11. Testing Strategy

**The testing pyramid:**

```
         /\
        /  \
       / E2E\      (full stack — we don't have these)
      /------\
     / Integ  \    (database + real services)
    /----------\
   /  Unit      \  (mocked dependencies — our 66 tests)
  /______________\
```

Our 66 tests are all unit tests. They run in ~0.5 seconds and need nothing except Python.

**What mocking means:**
A mock is a fake object that pretends to be something else. Instead of calling the real Yahoo Finance API (which requires internet and takes 2 seconds), we create a `MagicMock` that instantly returns whatever data we want.

```python
@patch("src.ingestion.fetcher.yfinance.Ticker")
def test_fetch_returns_dict(mock_ticker_class):
    # Set up the mock to return fake data
    mock_ticker = MagicMock()
    mock_ticker.history.return_value = fake_dataframe
    mock_ticker_class.return_value = mock_ticker

    # Now when the code calls yfinance.Ticker("AAPL"), it gets our mock
    result = fetch_current_price("AAPL")
    assert result["price"] == 189.42
```

**Why mock?**
- Speed: real API calls take 1-2s each; 12 tests × 2s = 24 seconds just for the fetcher tests
- Reliability: if Yahoo Finance is down, your tests shouldn't fail
- Control: you can simulate edge cases (empty response, network error) that are hard to reproduce with real APIs

**Mocking the database:**
```python
mock_session = MagicMock()
mock_query = MagicMock()
mock_session.query.return_value = mock_query
mock_query.filter.return_value.order_by.return_value.all.return_value = [row1, row2]
```
This mimics SQLAlchemy's fluent query interface: `.query().filter().order_by().all()` — each method returns an object with more methods, so we mock the entire chain.

**What each test file covers:**

`test_fetcher.py` (12 tests):
- Returns correct dict structure with right types
- Symbol is always uppercased
- Returns `None` for empty response
- Returns `None` for zero price
- Handles network exceptions

`test_database.py` (9 tests):
- Table name is `stock_prices`
- All columns exist with correct types
- Can insert and retrieve a row (SQLite in-memory)
- Auto-increment ID works
- Default volume is 0
- `repr()` contains symbol and price

`test_pipeline.py` (25 tests):
- `validate_record()`: valid record passes, missing field fails, zero price fails, etc.
- `transform()`: valid records become StockPrice objects, invalid are dropped
- `load()`: insert → inserted count increments, duplicate → skipped count increments, exception → failed count increments

`test_anomaly_detector.py` (8 tests):
- Stable prices → no anomaly
- Price spike → anomaly with direction="spike", z_score > 2.5
- Price drop → anomaly with direction="drop", z_score < -2.5
- < 3 rows → skip (no anomaly)
- All prices identical → skip (stdev=0)
- Multiple symbols → independent results
- Anomaly fields are all populated correctly
- Empty symbols list → returns immediately

`test_email_alerter.py` (9 tests):
- Empty anomalies → returns False
- Missing user → returns False
- Missing password → returns False
- Missing recipient → returns False
- Valid inputs → SMTP called, starttls called, login called, sendmail called
- Auth error → returns False gracefully
- Network error → returns False gracefully
- Multiple anomalies → single email (not one per anomaly)

---

## 12. Key Concepts Glossary

**APScheduler** — Advanced Python Scheduler. A library that runs Python functions on a schedule (like cron, but inside your Python process). We use `BlockingScheduler` which keeps the process alive.

**ASCII diagram** — A diagram drawn using text characters (+, -, |, ▶, etc.). Used in documentation because they render in any editor, terminal, or plain-text file without needing image uploads.

**Bandit** — A static analysis tool for Python security. "Static" means it reads the code without running it. It checks for patterns associated with vulnerabilities.

**CIDR notation** — A way of expressing an IP address range. `10.0.0.0/16` means "all IPs from 10.0.0.0 to 10.0.255.255" (65,536 addresses). The `/16` is the prefix length — how many bits are fixed.

**Container** — A lightweight, isolated process that packages an application with all its dependencies. Runs the same way on any machine.

**Context manager** — A Python pattern using the `with` statement that guarantees setup and teardown happens correctly (even if an exception is raised). `with get_session() as session:` always closes the session.

**Counter** (Prometheus) — A metric that only increases. Used for "how many times has X happened." Reset to 0 on process restart.

**CVE** — Common Vulnerabilities and Exposures. A standardised identifier for a publicly known security vulnerability. Format: CVE-YEAR-NUMBER, e.g. CVE-2024-3094.

**Dataclass** — A Python class with `@dataclass` decorator that automatically generates `__init__`, `__repr__`, and `__eq__` methods from type-annotated class attributes.

**Dependency injection** — Passing dependencies (like a database session) as function parameters instead of creating them inside the function. Makes code testable.

**ETL** — Extract, Transform, Load. The three-phase data pipeline pattern: pull raw data, clean it, store it.

**Gauge** (Prometheus) — A metric that can go up or down. Used for "what is X right now."

**Idempotent** — An operation that produces the same result whether you run it once or a hundred times. Our pipeline is idempotent: inserting the same price twice has the same result as inserting it once (due to the UNIQUE constraint).

**IaC (Infrastructure as Code)** — Managing cloud resources using code files instead of manual console clicks.

**Image** (Docker) — A read-only blueprint for a container. Built from a Dockerfile.

**Index** (database) — A data structure that speeds up queries. A B-tree index on `(symbol, fetched_at)` means lookups by symbol and time are O(log n) instead of O(n).

**MagicMock** — A Python mock object that automatically creates attributes and methods as needed. Used in tests to replace real dependencies.

**Named volume** (Docker) — Persistent storage managed by Docker. Survives container restarts and rebuilds. Only deleted with `docker compose down -v`.

**ORM** — Object-Relational Mapper. Software that maps Python classes to database tables. SQLAlchemy is our ORM.

**Parameterised query** — A SQL query where user input is passed as a parameter, not concatenated into the SQL string. Prevents SQL injection attacks.

**pip-audit** — A tool that checks installed Python packages against the Open Source Vulnerabilities database for known CVEs.

**Prometheus exposition format** — A plain-text format for exposing metrics over HTTP. Each line is `metric_name{labels} value timestamp`.

**PromQL** — Prometheus Query Language. Used to query time-series metrics stored in Prometheus.

**SAST** — Static Application Security Testing. Scanning source code for vulnerabilities without running it (Bandit).

**SCA** — Software Composition Analysis. Scanning dependencies for known vulnerabilities (pip-audit).

**Scraping** (Prometheus) — The act of Prometheus sending an HTTP GET to `/metrics` and collecting the values. Opposite of "pushing."

**Security group** (AWS) — A virtual firewall for EC2 and RDS resources. Rules define what traffic is allowed in (ingress) and out (egress).

**SMTP** — Simple Mail Transfer Protocol. The standard protocol for sending email between servers.

**STARTTLS** — A command that upgrades an existing plain-text connection to an encrypted TLS connection. Used by email clients on port 587.

**State file** (Terraform) — A JSON file (`terraform.tfstate`) that records what infrastructure Terraform created. Used to compute diffs on subsequent `terraform plan` runs.

**Subnet** — A subdivision of a VPC's IP address range. Public subnets route to the internet; private subnets don't.

**TIMESTAMPTZ** — PostgreSQL timestamp with time zone. Always stored as UTC, displayed in the session's timezone.

**VPC** — Virtual Private Cloud. Your isolated section of AWS's network. All your resources live inside it.

**Z-score** — A statistical measure of how many standard deviations a value is from the mean. Formula: `z = (x - μ) / σ`. Negative Z-score means below average; positive means above.

---

## 13. Interview Preparation

These are the questions you are most likely to be asked. Read the answers below and practice saying them out loud in your own words.

---

### "Walk me through the architecture of your stock analytics platform."

Start with the data source and trace the flow:

> "Live stock prices come from Yahoo Finance every 60 seconds. A Python ETL pipeline extracts the raw data, validates and normalises it, then stores it in PostgreSQL. Grafana reads from PostgreSQL directly to display live price charts. Separately, Prometheus scrapes a metrics endpoint on the app to track pipeline health — things like how many rows were inserted and how long each run took.
>
> A second process runs in parallel: it reads 20 days of price history from the database, computes Z-scores for each stock, and sends an email via Gmail SMTP if any score exceeds 2.5. Everything runs in Docker Compose — five containers that all talk to each other on a shared network.
>
> GitHub Actions runs on every push: ruff linting, 66 pytest tests, Bandit security scan, and pip-audit dependency scan. I also wrote Terraform to deploy the whole stack to AWS when I get an account."

---

### "What is a Z-score and why did you use it for anomaly detection?"

> "A Z-score measures how many standard deviations a value is from the mean of a reference dataset. The formula is `(x - μ) / σ`. I used it instead of a simple percent threshold because different stocks have different volatility. A 3% move on Tesla is routine — its standard deviation is maybe 4%. A 3% move on Apple is unusual — its standard deviation is maybe 1%. A fixed threshold would either spam alerts for volatile stocks or miss significant moves in stable ones. Z-score normalises by each stock's own variability, so the threshold is consistent regardless of the stock."

---

### "Why did you use Docker? What problem does it solve?"

> "The main problem Docker solves is 'works on my machine.' Without Docker, setting up this project means: install Python 3.12, install PostgreSQL, install Grafana, install Prometheus, configure each one, make sure versions are compatible. That's hours of work per machine and differs across operating systems.
>
> With Docker Compose, it's three commands: clone, copy the env file, `make up`. Docker packages each service with its exact dependencies. The same five containers run identically on my Windows laptop, a colleague's Mac, and the CI server running Linux."

---

### "What's the difference between Prometheus and Grafana?"

> "Prometheus is the collection and storage layer. It periodically scrapes metrics from my app's `/metrics` endpoint — things like how many rows were inserted, how many failed, how long each run took — and stores these time-series values in its own database.
>
> Grafana is the visualisation layer. It connects to both Prometheus (for pipeline health metrics) and PostgreSQL (for stock price data) and displays everything in dashboards. Grafana doesn't collect anything — it only reads and displays. You need both: Prometheus to collect and store metrics, Grafana to make them human-readable."

---

### "What is a connection pool and why does it matter?"

> "Opening a database connection is expensive — there's a TCP handshake, authentication, session setup. If every query opened and closed a connection, you'd spend most of your time just connecting. A connection pool opens N connections at startup and keeps them alive. When your code needs a connection, it borrows one from the pool, uses it, and returns it. The connection stays open and ready for the next request.
>
> I configured SQLAlchemy's pool with `pool_size=5` and `pool_pre_ping=True`. `pool_pre_ping` means SQLAlchemy tests each connection before lending it — if the database restarted and the connection is stale, the pool reconnects transparently."

---

### "What does parameterised mean and why does it prevent SQL injection?"

> "SQL injection is when an attacker puts SQL code into user input and it gets executed by the database. For example:
> ```python
> # DANGEROUS — never do this
> query = f"SELECT * FROM users WHERE name = '{user_input}'"
> # If user_input is: ' OR '1'='1
> # The query becomes: SELECT * FROM users WHERE name = '' OR '1'='1'
> # Which returns every user in the table
> ```
> Parameterised queries pass user input as a separate parameter, never concatenated into the SQL string:
> ```python
> # SAFE
> session.query(User).filter(User.name == user_input)
> # SQLAlchemy generates: SELECT * FROM users WHERE name = ?  with value=[user_input]
> # The database treats the input as data, never as SQL commands
> ```
> SQLAlchemy generates parameterised queries automatically, so SQL injection is impossible with our ORM."

---

### "Why do you use environment variables instead of hardcoding configuration?"

> "Three reasons. First, security: if I hardcoded `POSTGRES_PASSWORD = 'mypassword'` in a Python file and pushed to GitHub, that password is now public forever. Bots scan GitHub for exposed credentials constantly. Environment variables keep secrets out of source code entirely.
>
> Second, flexibility: the same code runs in different environments (my laptop, CI, production) with different configuration. The CI environment has a test database password; production has the real one. I don't change the code — I change the environment variables.
>
> Third, the `.env.example` file documents exactly what the app needs to run — like a configuration checklist. New developers copy it and fill in their values."

---

### "What is idempotency and where does it appear in your project?"

> "An idempotent operation produces the same result whether you run it once or a hundred times. In my pipeline, if the scheduler runs twice within the same second (due to a restart), it tries to insert prices it already inserted. The `UNIQUE (symbol, fetched_at)` constraint on the database table rejects duplicates with an IntegrityError. My load function catches that error and counts the row as 'skipped' rather than crashing. Running the pipeline 10 times in quick succession produces the same database state as running it once."

---

### "What would you do differently if this went to production?"

This shows maturity. Good answers include:

> "A few things. I'd add database migrations (using Alembic) instead of relying on `init.sql` — so schema changes can be applied to a live database without recreating it. I'd set up alerting on the Prometheus metrics too — email me if `pipeline_runs_total` stops increasing (pipeline died). I'd store the Terraform state in S3 with DynamoDB locking so a team can work on infrastructure simultaneously without conflicts. I'd also add a dead-letter queue for failed pipeline runs so I can replay them. And I'd use Secrets Manager (AWS) or Vault (HashiCorp) instead of environment variables for secrets in production."

---

*End of Project Guide. Use this document as a reference when studying individual components, preparing for interviews, or returning to the project after a break.*
