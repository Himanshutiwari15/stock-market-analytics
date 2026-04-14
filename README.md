# Real-Time Stock Market Analytics Platform

> A production-grade data platform that ingests live stock market data, processes it through an ETL pipeline, stores it in PostgreSQL, and visualizes it on a live Grafana dashboard — fully containerized with Docker, monitored with Prometheus, and deployed via GitHub Actions CI/CD.

[![CI](https://github.com/YOUR_USERNAME/stock-market-analytics/actions/workflows/ci.yml/badge.svg)](https://github.com/YOUR_USERNAME/stock-market-analytics/actions)

---

## What This Project Does

1. **Fetches** live stock prices (AAPL, GOOGL, MSFT, TSLA) every 60 seconds from Yahoo Finance
2. **Cleans and validates** the data through an ETL pipeline
3. **Stores** the processed data in a PostgreSQL database
4. **Visualizes** price history and trends on a live Grafana dashboard
5. **Monitors** the pipeline itself with Prometheus (error rates, run counts, latency)
6. **Alerts** via email when anomalies are detected (price spikes or drops > 3%)
7. **Scans** for security vulnerabilities automatically on every commit

---

## Architecture

```
Yahoo Finance API
      │
      ▼
┌─────────────┐     ┌──────────────────┐     ┌──────────────┐
│  Fetcher    │────▶│  ETL Pipeline    │────▶│  PostgreSQL  │
│ (yfinance)  │     │ extract/         │     │  Database    │
└─────────────┘     │ transform/       │     └──────┬───────┘
                    │ load             │            │
                    └──────────────────┘            │
                                                    ▼
                    ┌─────────────────────────────────────────┐
                    │              Grafana Dashboard           │
                    │     (live charts, auto-refresh 30s)      │
                    └─────────────────────────────────────────┘

                    ┌──────────────┐     ┌─────────────────┐
                    │  Prometheus  │────▶│  Grafana Alerts  │
                    │  (metrics)   │     │  (ops dashboard) │
                    └──────────────┘     └─────────────────┘

                    ┌──────────────────────────────────────┐
                    │         GitHub Actions CI/CD          │
                    │  lint → test → security scan → build  │
                    └──────────────────────────────────────┘
```

---

## Quick Start

### Prerequisites
- Docker Desktop (with WSL 2 on Windows)
- Git

### Run in 3 commands

```bash
# 1. Clone the repository
git clone https://github.com/YOUR_USERNAME/stock-market-analytics.git
cd stock-market-analytics

# 2. Set up your environment variables
cp .env.example .env
# Edit .env and fill in your values (see .env.example for guidance)

# 3. Start everything
make up
```

Then open:
- **Grafana dashboard:** http://localhost:3000 (login: admin / your GF_SECURITY_ADMIN_PASSWORD)
- **Prometheus metrics:** http://localhost:9090

---

## Tech Stack

| Component | Technology | Why |
|-----------|-----------|-----|
| Language | Python 3.11 | Strong data ecosystem, readable |
| Data Source | Yahoo Finance (yfinance) | Free, no API key, real data |
| Database | PostgreSQL 15 | Industry standard, great for time-series |
| Containerization | Docker + Docker Compose | Reproducible, portable |
| Dashboards | Grafana | Industry standard visualization |
| Monitoring | Prometheus | Industry standard metrics |
| CI/CD | GitHub Actions | Runs tests + security on every commit |
| Security Scanning | Bandit + Safety | Python-native vulnerability detection |
| Alerting | Gmail SMTP | Price anomaly email notifications |
| Infrastructure | Terraform (AWS) | Infrastructure as Code |

---

## Development Commands

```bash
make up        # Start all services (Docker Compose)
make down      # Stop all services
make test      # Run test suite (pytest)
make lint      # Check code style (ruff)
make format    # Auto-format code (ruff)
make security  # Run security scans (bandit + safety)
make logs      # Tail all service logs
make build     # Rebuild Docker images
make clean     # Remove Python cache files
make help      # Show all commands
```

---

## Project Structure

See [STRUCTURE.md](STRUCTURE.md) for the full directory layout with explanations.

---

## Security

See [docs/SECURITY.md](docs/SECURITY.md) for the security checklist and practices.

No API keys or secrets are ever hardcoded. All secrets are loaded from `.env` (which is gitignored). See `.env.example` for the full list of required environment variables.

---

## Build Plan

See [PLAN.md](PLAN.md) for the phased build plan and current progress.

---

## What I Learned

*(To be filled in during Phase 12 — final documentation)*

---

*Built as a portfolio project demonstrating data engineering, DevOps, and production observability practices.*
