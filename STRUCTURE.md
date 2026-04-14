# Project Structure

## Folder Tree

```
stock-market-analytics/
│
├── .github/
│   └── workflows/
│       ├── ci.yml                  # Main CI pipeline: lint, test, Docker build
│       └── security.yml            # Bandit + Safety security scanning
│
├── docker/
│   ├── app/
│   │   └── Dockerfile              # Containerizes the Python application
│   └── postgres/
│       └── init.sql                # Runs on first DB startup to create tables
│
├── docs/
│   ├── ARCHITECTURE.md             # System design, component diagram, data flow
│   ├── RUNBOOK.md                  # How to start, stop, troubleshoot, and scale
│   ├── API.md                      # Yahoo Finance API usage and data contracts
│   └── SECURITY.md                 # Security checklist and hardening practices
│
├── infrastructure/                 # Terraform IaC — Phase 10 (Optional / AWS)
│   ├── main.tf                     # Root Terraform config
│   ├── variables.tf                # Input variables (region, instance type, etc.)
│   ├── outputs.tf                  # Exported values (IPs, DNS names, etc.)
│   └── modules/
│       ├── ec2/                    # EC2 instance for running the app
│       └── rds/                    # RDS PostgreSQL instance
│
├── monitoring/
│   ├── grafana/
│   │   ├── provisioning/
│   │   │   ├── datasources/
│   │   │   │   └── postgres.yml    # Auto-connects Grafana to PostgreSQL
│   │   │   └── dashboards/
│   │   │       └── dashboard.yml   # Tells Grafana where to find dashboard JSONs
│   │   └── dashboards/
│   │       └── stock_overview.json # The actual dashboard definition (version-controlled)
│   └── prometheus/
│       └── prometheus.yml          # Scrape config: which targets Prometheus monitors
│
├── src/
│   ├── alerts/
│   │   ├── __init__.py
│   │   ├── detector.py             # Watches for price spikes/drops beyond threshold
│   │   └── notifier.py             # Sends email alerts via Gmail SMTP
│   │
│   ├── database/
│   │   ├── __init__.py
│   │   ├── connection.py           # Manages the PostgreSQL connection pool
│   │   └── models.py               # SQLAlchemy table definitions (ORM layer)
│   │
│   ├── ingestion/
│   │   ├── __init__.py
│   │   └── fetcher.py              # Fetches live data from Yahoo Finance (yfinance)
│   │
│   ├── monitoring/
│   │   ├── __init__.py
│   │   └── metrics.py              # Exposes Prometheus metrics (counters, gauges)
│   │
│   ├── pipeline/
│   │   ├── __init__.py
│   │   ├── extract.py              # Step 1: Pull raw data from the fetcher
│   │   ├── transform.py            # Step 2: Clean, validate, and normalize
│   │   ├── load.py                 # Step 3: Write clean data to PostgreSQL
│   │   └── scheduler.py            # Runs the full ETL pipeline on a timer
│   │
│   └── config.py                   # Single source of truth for all config values
│
├── tests/
│   ├── conftest.py                 # Shared pytest fixtures (DB connections, mocks)
│   ├── test_fetcher.py             # Tests for the ingestion fetcher
│   ├── test_database.py            # Tests for DB connection and models
│   ├── test_pipeline.py            # Tests for ETL transform logic
│   ├── test_detector.py            # Tests for anomaly detection logic
│   └── test_notifier.py            # Tests for alert sending (with SMTP mocked)
│
├── .bandit                         # Bandit security scanner configuration
├── .env                            # YOUR SECRETS — never committed to git
├── .env.example                    # Template with placeholder values — safe to commit
├── .gitignore                      # Prevents secrets, caches, and junk from git
├── CLAUDE.md                       # Project conventions for AI assistant sessions
├── docker-compose.yml              # Starts all services: app, postgres, grafana, prometheus
├── Makefile                        # Dev shortcuts: make up, make test, make lint
├── PLAN.md                         # Phased project plan
├── README.md                       # Public-facing documentation (filled in Phase 12)
├── requirements.txt                # Pinned Python dependencies
└── STRUCTURE.md                    # This file
```

---

## Why This Structure?

### `src/` — Application Code
All Python application code lives here, organized by responsibility:
- `ingestion/` — knows how to *get* data from the outside world
- `pipeline/` — knows how to *process* data (ETL)
- `database/` — knows how to *store* data
- `alerts/` — knows how to *react* to data
- `monitoring/` — knows how to *instrument* the app

Each subdirectory is its own Python package (has `__init__.py`). They are kept separate because each one has a different job, different dependencies, and different test requirements. This is called *separation of concerns*.

### `tests/` — Test Files
All tests live in one flat directory mirroring `src/`. This is the standard pytest convention and makes it easy to run all tests with one command: `pytest tests/`.

### `docker/` — Container Definitions
Dockerfiles and any container-specific config files. Separating these from `src/` keeps the app code clean and makes it clear what is "application" vs. "deployment".

### `monitoring/` — Observability Config
Grafana and Prometheus configuration files. These are versioned alongside the code so the monitoring setup is reproducible. No clicking in UIs — everything is defined as config files.

### `infrastructure/` — Cloud Provisioning
Terraform files that define the cloud resources. Optional for this project, but included so the structure is production-ready.

### `.github/workflows/` — CI/CD Pipelines
GitHub Actions workflow files. Every push triggers the pipeline defined here. Having this at the repo root in `.github/` is the GitHub standard — the platform picks it up automatically.

### Root-Level Files
- `docker-compose.yml` — at root because it orchestrates the entire project
- `Makefile` — at root because it's the developer interface (`make up`, `make test`)
- `.env` / `.env.example` — at root by convention (dotenv tools expect them here)
- `requirements.txt` — at root by Python convention

---

*Generated by Claude Code — your DevOps mentor for this project.*
