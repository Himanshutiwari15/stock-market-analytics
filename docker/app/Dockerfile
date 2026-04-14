# =============================================================
# docker/app/Dockerfile — Python ETL Pipeline Container
# =============================================================
# This file describes how to BUILD the Docker image for our app.
# An image is like a recipe: follow these steps and you get an
# identical, reproducible environment on any machine.
#
# KEY CONCEPT — Docker layers and caching:
#   Every instruction (FROM, RUN, COPY, etc.) creates a "layer" —
#   a snapshot of the filesystem at that moment.
#   Docker CACHES layers. If nothing changed in that step or any
#   step before it, Docker reuses the cached layer instead of
#   re-running the instruction.
#
# KEY OPTIMISATION — separate dependencies from source code:
#   WRONG order (slow rebuilds):
#     COPY . .              ← every code change invalidates this
#     RUN pip install ...   ← forces full reinstall on every code change
#
#   RIGHT order (fast rebuilds):
#     COPY requirements.txt .   ← only changes when you add/remove a package
#     RUN pip install ...       ← cached unless requirements.txt changed
#     COPY src/ ./src/          ← invalidated on code changes, but no pip install
#
#   Result: code changes rebuild in seconds, not minutes.
#
# BUILD CONTEXT:
#   This Dockerfile is built with the PROJECT ROOT as the context.
#   That is set in docker-compose.yml:
#     build:
#       context: .                        ← project root
#       dockerfile: docker/app/Dockerfile ← this file
#   So paths like "requirements.txt" and "src/" refer to the
#   project root, not to docker/app/.
# =============================================================

# --- Base image ---
# "FROM" is always the first instruction. It sets the starting point.
# python:3.12-slim = official Python 3.12 on Debian "slim" (~130 MB).
#   - "slim" strips compilers, headers, and docs — enough to run Python,
#     not enough to compile C extensions (we use psycopg2-binary, which
#     ships pre-compiled, so we don't need a compiler).
#   - We pin to 3.12-slim, not python:latest.
#     "latest" is a moving target — Docker would silently pull 3.13,
#     3.14, … and potentially break our code on future docker compose pulls.
FROM python:3.12-slim

# --- Suppress interactive prompts from APT ---
# If any RUN step installs system packages, APT might pause to ask
# questions (timezone, keyboard layout, etc.).
# Setting this env var tells APT to always choose the default answer.
# Harmless to set even if we never call APT directly.
ENV DEBIAN_FRONTEND=noninteractive

# --- Working directory inside the container ---
# Every subsequent COPY, RUN, and CMD is relative to /app.
# /app is the conventional location for application code in containers.
# Docker creates the directory if it does not exist.
WORKDIR /app

# -------------------------------------------------------
# STEP 1 — Install Python dependencies
# -------------------------------------------------------
# Copy ONLY requirements.txt first (not the whole project).
# This layer is only invalidated when requirements.txt changes.
# Your daily code edits won't touch requirements.txt, so this
# layer stays cached and pip install is skipped on most rebuilds.
COPY requirements.txt .

# Install all packages listed in requirements.txt.
# --no-cache-dir: skip pip's download cache inside the image.
#   We install once and never update — the cache is wasted space.
#   Omitting it would add ~50–100 MB of cached wheels to the image.
RUN pip install --no-cache-dir -r requirements.txt

# -------------------------------------------------------
# STEP 2 — Copy application source code
# -------------------------------------------------------
# Now copy the source code. This layer IS invalidated on every code
# change — but that's fine because there's no slow pip install here.
# The rebuild for a code change is essentially just a file copy: fast.
COPY src/ ./src/

# -------------------------------------------------------
# Container entry point
# -------------------------------------------------------
# CMD is the command Docker runs when you start the container.
# Equivalent to: python -m src.pipeline.scheduler
#
# WHY use a list (exec form) instead of a string (shell form)?
#   CMD ["python", "-m", "src.pipeline.scheduler"]   ← exec form
#   CMD "python -m src.pipeline.scheduler"            ← shell form
#
#   Exec form: Python is PID 1 inside the container.
#     - OS signals (SIGTERM from "docker stop") are delivered directly
#       to Python, which is why our signal.signal(SIGTERM, shutdown)
#       in scheduler.py works correctly.
#   Shell form: wraps your command in /bin/sh -c "...", making sh PID 1.
#     - "docker stop" sends SIGTERM to sh, not to Python.
#       Python never sees it and can't shut down gracefully.
#   Always use exec form for containers that need clean shutdown.

# -------------------------------------------------------
# Expose the Prometheus metrics port
# -------------------------------------------------------
# EXPOSE documents that the container listens on port 8000.
# The actual port mapping to your host machine (8000:8000) is
# declared in docker-compose.yml under the app service "ports:".
# EXPOSE alone does nothing — it is metadata for documentation
# and tooling (docker inspect, docker-compose, Kubernetes, etc.).
EXPOSE 8000

CMD ["python", "-m", "src.pipeline.scheduler"]
