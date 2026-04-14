# Real-Time Stock Market Analytics Platform — Project Plan

## Your Environment Profile

| Item | Status |
|------|--------|
| OS | Windows 11 |
| Python | 3.11+ installed |
| VS Code | Installed |
| Git | Installed, no repo yet |
| Docker Desktop | NOT YET INSTALLED — setup covered in Pre-Phase |
| GitHub Account | Ready |
| AWS Account | Not available — Terraform phase is optional |
| Experience Level | Beginner (Python comfortable, Docker/CI/DevOps new) |
| Alerting Method | Email via SMTP (Gmail) |

---

## Pre-Phase: Environment Setup (before Phase 1 code)

**Goal:** Get your machine fully ready so every phase works without friction.

### Step 1 — Install Docker Desktop (Windows)

1. Download from: https://www.docker.com/products/docker-desktop/
2. During installation, choose **WSL 2** backend (required on Windows 11)
3. If prompted to install WSL 2, follow the link and run: `wsl --install` in PowerShell as Administrator
4. After install, open Docker Desktop and wait for the green "Engine running" indicator
5. Verify in terminal:
   ```bash
   docker --version
   docker compose version
   ```

> **Why WSL 2?** Docker Desktop on Windows uses a tiny Linux virtual machine under the hood (WSL 2). This gives you real Linux containers with native performance. Without WSL 2, Docker either won't work or runs much slower on Windows.

### Step 2 — Create GitHub Repository

1. Go to github.com and log in
2. Click **New repository**
3. Name it: `stock-market-analytics`
4. Set visibility to **Public** (required for a portfolio project employers can see)
5. Do NOT check "Initialize with README" — we'll push our own
6. Copy the remote URL (looks like: `https://github.com/yourusername/stock-market-analytics.git`)

### Step 3 — Initialize Local Git Repo

In the terminal, inside this project folder:
```bash
git init
git remote add origin https://github.com/yourusername/stock-market-analytics.git
```

### Step 4 — Install Python dependencies tooling

```bash
pip install --upgrade pip
pip install virtualenv
python -m virtualenv venv
# On Windows:
venv\Scripts\activate
# On Mac/Linux:
source venv/bin/activate
```

> **Why virtualenv?** A virtual environment isolates this project's Python packages from your system Python. Without it, installing packages for this project could break other Python projects on your machine.

---

## Phase 1 — Project Foundation and Folder Structure

**What we're building:** The skeleton of the entire project — all directories, config files, security baseline, and the first committed codebase.

**Why this comes first:** Professional projects are navigable by anyone. A clear structure prevents chaos as complexity grows. Setting conventions now means you never have to untangle a mess later.

**Files to create:**
- All project directories
- `.gitignore` (Python + Docker + env file rules)
- `requirements.txt` (pinned Python dependencies)
- `README.md` (skeleton — filled out in Phase 12)
- `CONVENTIONS.md` (project coding conventions and guidelines)
- `docs/SECURITY.md` (security checklist)
- `.env.example` (template for environment variables — safe to commit)
- `Makefile` (convenience commands)

**Teaching topics:**
- Why we pin dependency versions (`requests==2.31.0` not `requests`)
- What `.gitignore` does and why `.env` MUST be in it from day one
- What a Makefile is and why DevOps teams use them
- Git branching strategy for solo portfolio projects

**Verification:** `git status` shows all files tracked. `.env` is NOT in the list. `make help` shows available commands.

---

## Phase 2 — Data Ingestion Script

**What we're building:** A Python script that fetches live stock/crypto price data from Yahoo Finance and returns clean, structured data.

**Why Yahoo Finance (yfinance)?** It is completely free, requires zero API keys, and returns pandas DataFrames. This is the right choice for a beginner — you get real data immediately with no account setup. We design the code so swapping to Alpha Vantage or Polygon.io later takes minutes.

**Files to create/modify:**
- `src/ingestion/fetcher.py` — core data fetching logic
- `src/ingestion/__init__.py`
- `src/config.py` — loads all environment variables centrally
- `tests/test_fetcher.py` — unit tests with mocked API calls
- `requirements.txt` — add yfinance, pandas, python-dotenv, pytest

**Teaching topics:**
- Environment variables vs. hardcoded values — the security argument
- What a pandas DataFrame is and why data engineers love it
- How to write testable code by separating concerns
- Error handling: what happens when the API is down or returns bad data

**Verification:** `python src/ingestion/fetcher.py` prints live AAPL price data in the terminal.

---

## Phase 3 — Database Setup and Storage Layer

**What we're building:** A PostgreSQL database (running in Docker) with a designed schema for stock price time-series data, and a Python module to read/write from it.

**Why PostgreSQL?** It is the industry standard for structured data. It handles time-series queries, JSON, and complex aggregations well. Every data engineering job description lists it. Free and open source.

**Files to create/modify:**
- `docker/postgres/init.sql` — schema definition (tables, indexes)
- `src/database/connection.py` — connection pool manager
- `src/database/models.py` — table definitions (SQLAlchemy ORM)
- `src/database/__init__.py`
- `docker-compose.yml` — PostgreSQL service definition
- `tests/test_database.py`

**Teaching topics:**
- What Docker Compose does vs. plain Docker run commands
- What an ORM is and when raw SQL is better than SQLAlchemy
- Connection pooling — why opening a new DB connection per query kills performance
- Schema design for time-series stock data

**Verification:** `docker compose up postgres -d` starts the database. Python script inserts a test row and reads it back successfully.

---

## Phase 4 — ETL Pipeline (Extract, Transform, Load)

**What we're building:** A scheduled pipeline: fetch data → validate and clean it → store in PostgreSQL. Runs automatically every 60 seconds.

**Why ETL is the backbone of data engineering:** Raw API data is messy — missing values, wrong data types, duplicate records, out-of-order timestamps. A proper ETL layer ensures only clean, consistent, trustworthy data enters your database. This is non-negotiable in production.

**Files to create/modify:**
- `src/pipeline/extract.py` — calls the fetcher
- `src/pipeline/transform.py` — cleans, validates, normalizes data
- `src/pipeline/load.py` — writes clean data to PostgreSQL
- `src/pipeline/scheduler.py` — runs the full pipeline on a timer
- `src/pipeline/__init__.py`
- `tests/test_pipeline.py`

**Teaching topics:**
- ETL vs. ELT — what's the difference and when to use each
- Data validation patterns: type checks, range checks, null handling
- Idempotency — what it means and why a pipeline must be safe to run twice
- Scheduling: cron vs. APScheduler vs. Airflow (and when each is appropriate)

**Verification:** Pipeline runs every 60 seconds. Data accumulates in PostgreSQL. Running the pipeline twice does not create duplicate rows.

---

## Phase 5 — Docker and Docker Compose for All Services

**What we're building:** A complete `docker-compose.yml` that orchestrates all services: Python app, PostgreSQL, Prometheus, and Grafana. One command starts everything.

**Why this phase is the project's centrepiece:** `docker compose up` and the entire platform is running. That is what makes this portfolio-grade. Any interviewer can clone your repo and see a live system in under 5 minutes.

**Files to create/modify:**
- `docker/app/Dockerfile` — containerizes the Python app
- `docker-compose.yml` — all four services wired together with networking and volumes
- `.env.example` — environment variable template (safe to commit)
- `docker/.dockerignore`

**Teaching topics:**
- How a Dockerfile works layer by layer (and why layer order matters for build speed)
- Why `.dockerignore` matters (keeps images small and secure)
- Docker networking: how containers find each other by service name
- Volume mounts: how data survives container restarts
- Health checks: making sure dependencies start before dependent services

**Verification:** `docker compose up --build` starts all services. Python app connects to PostgreSQL inside Docker successfully. Check `docker compose ps` to see all services healthy.

---

## Phase 6 — Grafana Dashboard Setup

**What we're building:** A live Grafana dashboard displaying stock price history, volume, and trends — auto-refreshing every 30 seconds from PostgreSQL data.

**Why Grafana?** It is the industry standard for operational dashboards and data visualization. A live, beautiful dashboard in your portfolio README screenshot is one of the most immediately impressive things you can show an employer.

**Files to create/modify:**
- `monitoring/grafana/provisioning/datasources/postgres.yml`
- `monitoring/grafana/provisioning/dashboards/dashboard.yml`
- `monitoring/grafana/dashboards/stock_overview.json`
- `docker-compose.yml` — add Grafana service

**Teaching topics:**
- Grafana provisioning: auto-configuring dashboards via config files (vs. clicking in the UI)
- Writing SQL queries for time-series visualization
- Dashboard design principles for financial data
- Exporting dashboards as JSON for version control (so teammates get the same dashboard)

**Verification:** Open `http://localhost:3000`. Login with admin/admin. See live stock price charts rendering from PostgreSQL.

---

## Phase 7 — Prometheus Monitoring and Alerting

**What we're building:** Prometheus scrapes custom metrics from the Python app (pipeline run counts, error rates, latency). Grafana shows these operational metrics.

**Why Prometheus + custom app metrics?** This demonstrates you understand observability — tracking not just *what* the data is, but *how the system is performing*. This is a senior engineering skill that beginners rarely demonstrate. It makes your project look genuinely production-grade.

**Files to create/modify:**
- `monitoring/prometheus/prometheus.yml` — scrape configuration
- `src/monitoring/metrics.py` — custom Prometheus metrics (counters, gauges)
- `docker-compose.yml` — add Prometheus service

**Teaching topics:**
- The four golden signals of production observability (latency, traffic, errors, saturation)
- Prometheus data model: counters vs. gauges vs. histograms
- Pull vs. push monitoring models (Prometheus pulls, others push)
- Alerting rules in Prometheus vs. Grafana alerts

**Verification:** Open `http://localhost:9090` (Prometheus UI). Query `pipeline_runs_total`. See data. Grafana shows an ops panel alongside the stock dashboard.

---

## Phase 8 — GitHub Actions CI/CD Pipeline

**What we're building:** Automated CI that runs on every push: install deps → lint → run tests → build Docker image → report pass/fail. The main branch is always green.

**Why CI/CD is non-negotiable for a professional project:** This is what separates a hobby coder from a software engineer. Every professional team uses CI. A repository with a green Actions badge and a visible pipeline history shows you work the way real teams work.

**Files to create/modify:**
- `.github/workflows/ci.yml` — main CI pipeline
- `Makefile` — add `make test`, `make lint`, `make build` targets

**Teaching topics:**
- What CI/CD means (Continuous Integration / Continuous Delivery)
- GitHub Actions syntax: workflows, jobs, steps, actions
- Why tests run in CI (not just locally) — reproducibility
- Secrets in GitHub Actions: how to add them and why you never hardcode them
- Docker build caching in CI for faster pipelines

**Verification:** Push a commit to GitHub. Go to the Actions tab — see the pipeline running and turning green. Intentionally break a test. See it turn red. Fix it. See it go green again.

---

## Phase 9 — Security Scanning Integration

**What we're building:** Automated Python security scanning with Bandit and dependency vulnerability checking with Safety — both integrated into the CI pipeline.

**Why Bandit instead of SonarQube?** SonarQube requires a dedicated server and significant configuration. Bandit is Python-native, runs in 2 seconds, catches real vulnerabilities, and is used in production at real companies. For a portfolio project, it is exactly the right tool.

**Files to create/modify:**
- `.github/workflows/ci.yml` — add Bandit and Safety steps
- `docs/SECURITY.md` — filled-out security checklist
- `.bandit` — Bandit configuration
- `Makefile` — add `make security` command

**Teaching topics:**
- Common Python security vulnerabilities Bandit detects (hardcoded passwords, SQL injection, use of assert)
- Dependency supply chain attacks — why you check third-party packages
- How to read a Bandit report and triage findings (severity vs. confidence)
- The OWASP Top 10 — a beginner overview

**Verification:** `make security` runs locally and passes. CI fails if any HIGH severity issues are introduced.

---

## Phase 10 — Terraform Infrastructure as Code (OPTIONAL)

**Status: OPTIONAL** — requires creating an AWS free-tier account. This phase will be revisited once you decide whether to proceed.

**What we would build:** Terraform configuration to provision the entire infrastructure on AWS: an EC2 instance for the app, RDS PostgreSQL, S3 for backups, security groups, and IAM roles.

**Why it is valuable for a CV even if you do not deploy:** Terraform is one of the most in-demand DevOps skills in the market. Having `.tf` files in your repository that define real infrastructure shows you understand IaC concepts, even if the infra is not live.

**Files to create (if proceeding):**
- `infrastructure/main.tf`
- `infrastructure/variables.tf`
- `infrastructure/outputs.tf`
- `infrastructure/modules/ec2/`
- `infrastructure/modules/rds/`
- `infrastructure/terraform.tfvars.example`

**Decision point:** At the start of this phase, I will ask if you have created an AWS free-tier account. If not, we can still write the files for educational purposes without running `terraform apply`.

---

## Phase 11 — Anomaly Detection and Email Alerts

**What we're building:** A detector that monitors price changes and triggers an email alert via Gmail SMTP when a configurable threshold is crossed (e.g., price drops more than 3% in one interval).

**Why this is the "wow" feature:** This makes the system react to the real world. It demonstrates you built not just a data pipeline but an intelligent monitoring system. It is exactly what production trading risk systems do at their core — just simpler.

**Files to create/modify:**
- `src/alerts/detector.py` — anomaly detection logic (rolling window approach)
- `src/alerts/notifier.py` — email sender via smtplib
- `src/alerts/__init__.py`
- `tests/test_detector.py`
- `tests/test_notifier.py`
- `.env` — add Gmail SMTP credentials

**Teaching topics:**
- Anomaly detection approaches: z-score, percentage change, rolling window (we use rolling window — simplest and most explainable)
- How SMTP works and why you need a Gmail App Password (not your real password)
- Why we test notification logic separately from sending (mocking SMTP in tests)
- Rate limiting alerts — how to avoid sending 100 emails in a spike

**Verification:** Manually trigger a test alert from Python. Receive a formatted email with symbol, price change percentage, and timestamp.

---

## Phase 12 — Final Documentation and CV-Ready README

**What we're building:** A polished, professional README.md with architecture diagram, screenshots of the live dashboard, full setup instructions, and a technology decision log.

**Files to create/modify:**
- `README.md` — full project README (the public face of your work)
- `docs/ARCHITECTURE.md` — system design and component interaction
- `docs/RUNBOOK.md` — how to operate and troubleshoot the system
- `docs/API.md` — data source documentation

**Teaching topics:**
- What makes a README great (the "5 second test" — can a recruiter tell what this is in 5 seconds?)
- How to write a Mermaid architecture diagram (renders on GitHub)
- How to present this project confidently in a technical interview

**Verification:** Show the README to someone who has never seen the project. They can understand what it does, run it, and see it working.

---

## Phase Summary Table

| Phase | Name | Complexity | Key Output |
|-------|------|------------|------------|
| Pre | Environment Setup | Low | Docker + Git + GitHub repo ready |
| 1 | Project Foundation | Low | Clean folder structure, first commit |
| 2 | Data Ingestion | Low-Med | Live stock data fetching in Python |
| 3 | Database Setup | Medium | PostgreSQL running, data persisted |
| 4 | ETL Pipeline | Medium | Automated data pipeline running |
| 5 | Docker Compose | Medium | `docker compose up` starts everything |
| 6 | Grafana | Low-Med | Live stock dashboard in browser |
| 7 | Prometheus | Medium | App metrics + operational dashboard |
| 8 | GitHub Actions | Medium | Green CI badge on GitHub |
| 9 | Security Scanning | Low | Automated security checks in CI |
| 10 | Terraform | High (Optional) | AWS infrastructure as code |
| 11 | Anomaly Detection | Medium | Email alert on price spikes |
| 12 | Documentation | Low | CV-ready README with screenshots |

---

*This document tracks the phased build plan for the Stock Market Analytics Platform.*
