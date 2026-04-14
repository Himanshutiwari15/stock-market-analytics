# CONVENTIONS.md — Project Coding Conventions

## Project Overview

**Name:** Real-Time Stock Market Analytics Platform
**Purpose:** Production-grade portfolio project demonstrating data engineering, DevOps, and observability skills.

**Tech Stack:**
- Language: Python 3.12
- Data source: Yahoo Finance (yfinance) — no API key required
- Database: PostgreSQL (via Docker)
- Containerization: Docker + Docker Compose
- Monitoring: Prometheus + Grafana
- CI/CD: GitHub Actions
- Security scanning: Bandit + pip-audit
- Alerting: Email via Gmail SMTP
- IaC: Terraform (optional — no AWS account yet)

---

## Coding Conventions

### Python
- Python 3.12 only. Use type hints on all function signatures.
- Use `python-dotenv` to load `.env` — never hardcode config values.
- All app code lives under `src/`. Maintain the `src/ingestion/`, `src/pipeline/`, `src/database/`, `src/alerts/`, `src/monitoring/` layout.
- Use `src/config.py` as the single source of truth for all configuration values.
- Add docstrings and inline comments explaining *what* and *why*.

### Security (non-negotiable)
- `.env` is NEVER committed to git. Verify it is in `.gitignore` before every commit.
- `.env.example` contains all keys with placeholder values. This IS committed.
- No secrets, passwords, API keys, or tokens in any source file.
- Use parameterized queries for all database operations — never string-formatted SQL.
- Bandit must pass before any merge to main.

### Git
- `main` branch is always in a deployable, working state.
- Feature branches: `feature/short-description`
- Fix branches: `fix/short-description`
- Commit messages: imperative mood, present tense (e.g., "Add stock price fetcher", "Fix duplicate row insertion")
- Never commit: `.env`, `venv/`, `__pycache__/`, `.terraform/`, `*.pyc`

### Docker
- Always pin image versions (e.g., `python:3.12-slim`, not `python:latest`).
- All services defined in the root `docker-compose.yml`.
- Use `.dockerignore` to exclude `venv/`, `.env`, `__pycache__/`, `*.pyc`.
- Use named volumes for persistent data (PostgreSQL data).
- Add health checks to all services so Docker knows when they are ready.

### Database
- Schema is defined in `docker/postgres/init.sql`.
- Always use SQLAlchemy ORM models in `src/database/models.py` for Python-side queries.
- Raw SQL is acceptable for complex analytical queries — but always parameterized.
- Never use `ALTER TABLE` manually — schema changes go through migration files.

### Testing
- All tests live in `tests/`. Mirror the `src/` structure in test naming.
- Use `pytest` as the test runner.
- Mock all external API calls in unit tests (use `unittest.mock` or `pytest-mock`).
- Integration tests may connect to a real test database running in Docker.
- Minimum one test per module. Aim for the happy path + one error/edge case.

### Makefile Targets (standard interface)
```
make up       — docker compose up --build (starts all services)
make down     — docker compose down (stops all services)
make test     — pytest tests/
make lint     — ruff check src/ tests/
make format   — ruff format src/ tests/
make security — bandit -r src/ && pip-audit -r requirements.txt
make logs     — docker compose logs -f
make help     — show all targets
```

---

## Phase Status

- [x] Pre-phase: Environment setup (Python 3.12, venv, dependencies)
- [x] Phase 1: Project foundation and folder structure
- [x] Phase 2: Data ingestion script (yfinance via history(), 12 tests passing)
- [x] Phase 3: Database setup and storage layer
- [x] Phase 4: ETL pipeline
- [x] Phase 5: Docker and Docker Compose
- [x] Phase 6: Grafana dashboard
- [x] Phase 7: Prometheus monitoring
- [x] Phase 8: GitHub Actions CI/CD
- [x] Phase 9: Security scanning
- [x] Phase 10: Terraform IaC (written — not applied, no AWS account yet)
- [x] Phase 11: Anomaly detection and email alerts
- [x] Phase 12: Final documentation and CV-ready README
