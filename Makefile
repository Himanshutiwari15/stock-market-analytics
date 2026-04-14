# =============================================================
# Makefile — Developer convenience commands
# =============================================================
# A Makefile is a standard tool for defining project shortcuts.
# Instead of typing "docker compose up --build -d" every time,
# you just type "make up".
#
# WHY teams use Makefiles:
#   - Every developer uses the same commands
#   - New team members can run "make help" and know exactly what to do
#   - CI/CD can call the same targets (make test, make lint)
#   - Reduces errors from mistyped long commands
#
# USAGE:
#   make <target>    e.g.:  make up  |  make test  |  make help
# =============================================================

# .PHONY tells Make these are command names, not file names.
# Without this, Make would look for files named "up", "test", etc.
.PHONY: help up down build logs test lint format security clean shell-app shell-db

# -------------------------------------------------------
# Default target — runs when you type just "make"
# -------------------------------------------------------
help:
	@echo ""
	@echo "  ╔══════════════════════════════════════════════════╗"
	@echo "  ║   Real-Time Stock Market Analytics Platform      ║"
	@echo "  ╚══════════════════════════════════════════════════╝"
	@echo ""
	@echo "  DOCKER"
	@echo "    make up         Start all services (detached mode)"
	@echo "    make down       Stop and remove all containers"
	@echo "    make build      Rebuild Docker images (no cache)"
	@echo "    make logs       Tail logs from all services"
	@echo ""
	@echo "  DEVELOPMENT"
	@echo "    make test       Run the full test suite (pytest)"
	@echo "    make lint       Check code style (ruff)"
	@echo "    make format     Auto-fix code style (ruff)"
	@echo "    make security   Run Bandit + Safety security scans"
	@echo "    make clean      Remove Python cache files"
	@echo ""
	@echo "  DEBUGGING"
	@echo "    make shell-app  Open a shell inside the app container"
	@echo "    make shell-db   Open a psql shell in the database"
	@echo ""

# -------------------------------------------------------
# Docker targets
# -------------------------------------------------------

# Start all services defined in docker-compose.yml.
# --build: rebuild images if Dockerfile or code changed.
# -d: detached mode (runs in background, your terminal stays free).
up:
	docker compose up --build -d
	@echo ""
	@echo "  Services started:"
	@echo "    Grafana:    http://localhost:3000"
	@echo "    Prometheus: http://localhost:9090"
	@echo "    App logs:   make logs"
	@echo ""

# Stop all running containers and remove them.
# Volumes are preserved (your data survives).
# To also delete volumes: docker compose down -v
down:
	docker compose down

# Rebuild images completely (ignores cache).
# Use this when you change requirements.txt or the Dockerfile.
build:
	docker compose build --no-cache

# Follow logs from all services in real time.
# Ctrl+C to exit. To follow only one service: docker compose logs -f app
logs:
	docker compose logs -f

# -------------------------------------------------------
# Python / development targets
# -------------------------------------------------------

# Run the full test suite with verbose output.
# -v: show each test name as it runs.
# --tb=short: shorter traceback on failure (easier to read).
test:
	pytest tests/ -v --tb=short

# Check code for style issues without changing anything.
# Exit code 1 if any issues found (CI will fail).
lint:
	ruff check src/ tests/

# Automatically fix style issues where possible.
# This modifies your files in place — review the changes.
format:
	ruff format src/ tests/
	ruff check --fix src/ tests/

# -------------------------------------------------------
# Security targets
# -------------------------------------------------------

# Run both security tools.
# bandit:    scans Python source code for vulnerabilities (hardcoded secrets,
#            SQL injection patterns, use of insecure functions, etc.)
# pip-audit: checks all dependencies against the OSV vulnerability database.
#            Flags packages with known CVEs (Common Vulnerabilities and Exposures).
security:
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "Running Bandit (Python code scanner)..."
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	bandit -r src/ -c .bandit
	@echo ""
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "Running pip-audit (dependency CVE check)..."
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	pip-audit -r requirements.txt

# -------------------------------------------------------
# Cleanup
# -------------------------------------------------------

# Remove Python cache files and test artifacts.
# Safe to run at any time — only deletes generated files.
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name ".coverage" -delete 2>/dev/null || true
	find . -type d -name "htmlcov" -exec rm -rf {} + 2>/dev/null || true
	@echo "Cache cleared."

# -------------------------------------------------------
# Debugging helpers
# -------------------------------------------------------

# Open an interactive bash shell inside the running app container.
# Useful for debugging: you can run Python, check env vars, etc.
shell-app:
	docker compose exec app bash

# Open a psql (PostgreSQL command-line) shell in the database container.
# Useful for inspecting data, running manual queries, checking tables.
shell-db:
	docker compose exec postgres psql -U $${POSTGRES_USER} -d $${POSTGRES_DB}
