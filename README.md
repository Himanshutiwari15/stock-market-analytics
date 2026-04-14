# Real-Time Stock Market Analytics Platform

> A production-grade data engineering platform that ingests live stock prices, processes them through an ETL pipeline, stores them in PostgreSQL, visualizes them on a live Grafana dashboard, monitors the pipeline with Prometheus, and emails you when price anomalies are detected — fully containerized with Docker and deployed via GitHub Actions CI/CD.

[![CI](https://github.com/Himanshutiwari15/stock-market-analytics/actions/workflows/ci.yml/badge.svg)](https://github.com/Himanshutiwari15/stock-market-analytics/actions)
![Python](https://img.shields.io/badge/python-3.12-blue)
![Docker](https://img.shields.io/badge/docker-compose-2496ED)
![PostgreSQL](https://img.shields.io/badge/postgresql-15-336791)
![Tests](https://img.shields.io/badge/tests-66%20passing-brightgreen)
![License](https://img.shields.io/badge/license-MIT-green)

---

## What It Does

| # | Capability | Technology |
|---|-----------|-----------|
| 1 | Fetches live stock prices every 60 seconds | Yahoo Finance (yfinance) |
| 2 | Cleans, validates, and normalises the data | Python ETL pipeline |
| 3 | Stores time-series price data | PostgreSQL 15 |
| 4 | Visualises price history with live charts | Grafana (auto-refreshes every 30s) |
| 5 | Monitors the pipeline's own health | Prometheus + Grafana |
| 6 | Detects price anomalies using Z-score statistics | Custom Python detector |
| 7 | Sends email alerts when anomalies are found | Gmail SMTP |
| 8 | Scans for security vulnerabilities on every commit | Bandit + pip-audit (GitHub Actions) |
| 9 | Defines cloud infrastructure as code | Terraform (AWS EC2 + RDS) |

---

## Architecture

```
                        Yahoo Finance API
                               │
                    (fetches every 60 seconds)
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│                      Docker Compose Stack                        │
│                                                                  │
│  ┌─────────────────────┐          ┌───────────────────────────┐  │
│  │   app (ETL pipeline) │          │   alerts (anomaly runner) │  │
│  │                     │          │                           │  │
│  │  extract → transform │  writes  │  reads 20-day history     │  │
│  │       → load         │────────▶│  computes Z-scores        │  │
│  │                     │          │  sends email if |z| > 2.5 │  │
│  │  exposes :8000/metrics│         │                           │  │
│  └──────────┬──────────┘          └───────────────────────────┘  │
│             │  writes                         │                   │
│             ▼                                 ▼                   │
│  ┌──────────────────────┐       ┌─────────────────────────────┐  │
│  │  postgres :5432       │       │       Gmail SMTP             │  │
│  │  PostgreSQL 15        │       │  (HTML anomaly alert email) │  │
│  │  stock_prices table   │       └─────────────────────────────┘  │
│  └──────────┬───────────┘                                         │
│             │                                                     │
│     ┌───────┴────────┐                                            │
│     │                │                                            │
│     ▼                ▼                                            │
│  ┌────────────┐  ┌──────────────────┐                            │
│  │  grafana   │  │  prometheus      │                            │
│  │  :3000     │  │  :9090           │                            │
│  │            │  │                  │                            │
│  │  price     │◀─│  scrapes :8000   │                            │
│  │  dashboards│  │  /metrics every  │                            │
│  │  + ops     │  │  15s             │                            │
│  └────────────┘  └──────────────────┘                            │
└──────────────────────────────────────────────────────────────────┘

                    ┌──────────────────────────────────┐
                    │      GitHub Actions CI/CD         │
                    │                                   │
                    │  on every push to main:           │
                    │  ruff lint → pytest (66 tests)    │
                    │  → bandit → pip-audit             │
                    └──────────────────────────────────┘

                    ┌──────────────────────────────────┐
                    │      Terraform (AWS — optional)   │
                    │                                   │
                    │  VPC → EC2 (app) → RDS (postgres) │
                    │  Written, ready to apply          │
                    └──────────────────────────────────┘
```

---

## Quick Start

**Prerequisites:** Docker Desktop (WSL 2 backend on Windows), Git

```bash
# 1. Clone the repository
git clone https://github.com/Himanshutiwari15/stock-market-analytics.git
cd stock-market-analytics

# 2. Configure environment variables
cp .env.example .env
# Open .env and set POSTGRES_PASSWORD and GF_SECURITY_ADMIN_PASSWORD at minimum

# 3. Start all 5 services
make up
```

**Then open:**
| Service | URL | Credentials |
|---------|-----|-------------|
| Grafana dashboards | http://localhost:3000 | admin / (your GF_SECURITY_ADMIN_PASSWORD) |
| Prometheus metrics | http://localhost:9090 | — |
| App metrics endpoint | http://localhost:8000/metrics | — |
| PostgreSQL | localhost:5432 | (your .env values) |

---

## Email Alerts Setup

1. Enable 2-Step Verification on your Google account
2. Create a Gmail App Password at [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
3. Add to your `.env`:
   ```
   SMTP_USER=your.address@gmail.com
   SMTP_PASSWORD=your_16char_app_password
   ALERT_RECIPIENT=where_to_send@example.com
   ```
4. Test immediately (without waiting for a real anomaly):
   ```bash
   # Threshold of 0.1 will trigger on almost any price data
   ANOMALY_Z_SCORE_THRESHOLD=0.1 python -m src.alerts.runner --once
   ```

Alerts fire when a price is more than **2.5 standard deviations** from its 20-day rolling mean — a statistical threshold that catches genuine spikes while keeping false positives below 1.2%.

---

## Development Commands

```bash
make up        # Start all 5 Docker services (build if needed)
make down      # Stop all services
make test      # Run test suite — 66 tests, no Docker required
make lint      # ruff linter (style + unused imports)
make format    # ruff auto-formatter
make security  # bandit (source code) + pip-audit (dependencies)
make logs      # Tail logs from all services
make help      # Show all available commands
```

---

## Tech Stack

| Component | Technology | Why I chose it |
|-----------|------------|---------------|
| Language | Python 3.12 | Strong data ecosystem; type hints for safety |
| Data Source | Yahoo Finance (yfinance) | Free, no API key, real live data |
| Database | PostgreSQL 15 | Industry standard for time-series; TIMESTAMPTZ support |
| ORM | SQLAlchemy 2.0 | Prevents SQL injection; portable across DB engines |
| Containerisation | Docker + Docker Compose | Reproducible on any machine; matches production |
| Dashboards | Grafana 10.3 | Industry standard; provisioned-as-code (no manual setup) |
| Metrics | Prometheus | Pull-based scraping; integrates natively with Grafana |
| CI/CD | GitHub Actions | Free for public repos; runs on every push |
| SAST | Bandit | Python-specific security patterns (hardcoded secrets, SQLi) |
| Dependency scan | pip-audit | PyPA-maintained; no auth required; OSV database |
| Anomaly detection | Z-score (stdlib statistics) | Self-normalising per stock; no ML library needed |
| Email | smtplib + Gmail SMTP | Standard library; App Passwords isolate credentials |
| IaC | Terraform + AWS | Industry standard; EC2 + RDS defined as code |

---

## Project Structure

```
stock-market-analytics/
├── src/
│   ├── alerts/
│   │   ├── anomaly_detector.py  Z-score engine — queries DB, returns Anomaly dataclasses
│   │   ├── email_alerter.py     Gmail SMTP via STARTTLS — builds + sends HTML email
│   │   └── runner.py            Entry point — loop mode (Docker) or --once (manual)
│   ├── database/
│   │   ├── connection.py        SQLAlchemy connection pool + context manager
│   │   └── models.py            StockPrice ORM model (Numeric, TIMESTAMPTZ, unique constraint)
│   ├── ingestion/
│   │   └── fetcher.py           Fetches live prices via yfinance; returns typed dicts
│   ├── monitoring/
│   │   └── metrics.py           Prometheus counters + gauges exposed on :8000/metrics
│   ├── pipeline/
│   │   ├── extract.py           Step 1: pull raw data from fetcher
│   │   ├── transform.py         Step 2: validate, normalise, deduplicate
│   │   ├── load.py              Step 3: upsert to PostgreSQL (idempotent)
│   │   └── scheduler.py         APScheduler loop — runs ETL every N seconds
│   └── config.py                Single source of truth for all env-var config
├── tests/                       66 tests — all mocked, no Docker needed for CI
├── infrastructure/              Terraform IaC — VPC, EC2, RDS (ready to apply)
├── monitoring/                  Grafana + Prometheus config (provisioned as code)
├── docker/                      Dockerfile + PostgreSQL init.sql
├── .github/workflows/ci.yml     GitHub Actions: lint → test → security scan
├── docker-compose.yml           5 services: app, postgres, grafana, prometheus, alerts
└── Makefile                     Developer interface (make up / test / lint / security)
```

---

## Testing

```bash
make test
# or: pytest tests/ -v
```

**66 tests across 5 modules — zero external dependencies in CI:**

| Test file | What it covers | Strategy |
|-----------|---------------|----------|
| `test_fetcher.py` | Yahoo Finance data fetching | Mock yfinance API |
| `test_database.py` | ORM model, constraints, queries | SQLite in-memory |
| `test_pipeline.py` | ETL validate / transform / load | Mock DB session |
| `test_anomaly_detector.py` | Z-score logic, edge cases | Mock SQLAlchemy session |
| `test_email_alerter.py` | SMTP flow, error handling | Mock smtplib.SMTP |

**Edge cases covered:** spike detection, drop detection, zero std dev (flat price), insufficient data, auth failure, network error, missing credentials, multiple anomalies in one email.

---

## Security

- **No secrets in source code** — all credentials loaded from `.env` (gitignored)
- **Parameterised queries** — SQLAlchemy ORM prevents SQL injection
- **BANDIT** — static analysis on every CI run (checks for hardcoded secrets, dangerous calls)
- **pip-audit** — dependency CVE scan on every CI run (PyPA-maintained, no auth needed)
- **Gmail App Passwords** — SMTP uses a scoped credential, not the account password
- **Terraform** — RDS in private subnet (unreachable from internet); EC2 SSH restricted to single IP

See [docs/SECURITY.md](docs/SECURITY.md) for the full security checklist.

---

## Infrastructure as Code (Terraform)

The `infrastructure/` directory contains production-ready Terraform for AWS:

```
VPC (10.0.0.0/16)
├── Public subnets  (2 AZs) → EC2 t2.micro  (app server + Docker)
└── Private subnets (2 AZs) → RDS db.t3.micro (PostgreSQL 15, encrypted)

Security groups:
  EC2:  SSH from your IP only, :8000/:3000/:9090 open
  RDS:  :5432 from EC2 security group only (not internet)
```

To deploy when you have an AWS account:
```bash
cd infrastructure
cp terraform.tfvars.example terraform.tfvars
# Fill in your IP, key pair name, and DB password
export TF_VAR_db_password="your-strong-password"
terraform init && terraform plan && terraform apply
```

---

## Skills Demonstrated

This project was built to demonstrate production engineering practices end-to-end:

**Data Engineering**
- Designed a multi-stage ETL pipeline (extract → validate → transform → load) with idempotent upserts
- Modelled time-series data in PostgreSQL with appropriate types (TIMESTAMPTZ, NUMERIC), indexes, and unique constraints
- Implemented Z-score statistical anomaly detection without external ML libraries

**DevOps & Infrastructure**
- Orchestrated 5 Docker services with health checks, named volumes, and dependency ordering
- Built a CI/CD pipeline (GitHub Actions) that runs lint, tests, and two security scanners on every commit
- Wrote Terraform IaC for a full AWS deployment: VPC, public/private subnets, EC2, RDS

**Observability**
- Instrumented the pipeline with Prometheus counters and gauges (rows inserted, errors, run duration)
- Provisioned Grafana dashboards and datasources as code (no manual UI setup)
- Separated operational monitoring (Prometheus) from business monitoring (Grafana stock charts)

**Security**
- Enforced zero secrets in code via python-dotenv; verified by Bandit SAST on every CI run
- Scanned all dependencies for published CVEs using pip-audit (PyPA-maintained)
- Scoped database access with parameterised SQLAlchemy queries (no raw string SQL)

**Software Engineering**
- Used Python type hints, dataclasses, context managers, and dependency injection throughout
- Achieved 66 passing tests with zero external service dependencies in CI (full mocking strategy)
- Applied separation of concerns: each module has one job, one test file, one reason to change

---

## What I Learned

- **Docker networking:** how containers find each other by service name (Docker DNS), and why `POSTGRES_HOST=postgres` inside Docker vs `localhost` outside
- **Connection pooling:** why creating a new DB connection per query is expensive, and how SQLAlchemy's pool solves it with `pool_pre_ping` for idle connection recovery
- **Prometheus pull model:** why Prometheus scrapes targets instead of targets pushing to Prometheus — and why that matters for reliability
- **Z-score vs percent thresholds:** fixed percent thresholds spam alerts for volatile stocks; Z-score normalises by each stock's own variance
- **CI pipeline design:** why lint runs before tests (fast failures first), and why tests can't depend on real services (flakiness in shared environments)
- **Terraform modules:** how to split infrastructure into reusable modules with input variables and outputs, and why state must be stored remotely in teams
- **SMTP authentication:** the difference between OAuth and App Passwords, and why the latter is safer for programmatic access

---

*Built as a portfolio project demonstrating data engineering, DevOps, and production observability practices.*
