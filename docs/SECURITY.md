# Security Checklist

This document tracks the security posture of the Real-Time Stock Market Analytics Platform.
Use it as a checklist before any deployment and when reviewing new code.

---

## Secrets Management

- [ ] `.env` file is listed in `.gitignore` — **verify before every commit**
- [ ] No secrets, passwords, API keys, or tokens in any `.py`, `.yml`, `.json`, or `.tf` file
- [ ] `.env.example` contains only placeholder values (no real credentials)
- [ ] GitHub Actions repository secrets are used for any CI/CD credentials
- [ ] Docker environment variables are passed at container runtime, not baked into Docker images
- [ ] Terraform variable files (`*.tfvars`) are in `.gitignore`

## Authentication

- [ ] PostgreSQL password is strong (not "changeme") and set via `POSTGRES_PASSWORD` env var
- [ ] Grafana admin password is changed from default and set via `GF_SECURITY_ADMIN_PASSWORD`
- [ ] Gmail SMTP uses an App Password, not the real account password
- [ ] Default credentials on all services are changed before any public deployment

## Code Security (checked by Bandit)

- [ ] All database queries use SQLAlchemy ORM or parameterized statements — no string-formatted SQL
- [ ] Input data from Yahoo Finance API is validated before insertion into the database
- [ ] No use of `eval()` or `exec()` with any external or user-supplied data
- [ ] `bandit -r src/` passes with no HIGH or MEDIUM severity findings
- [ ] No use of Python's `pickle` module with untrusted data (deserialization attack vector)

## Dependencies (checked by Safety)

- [ ] All dependencies pinned to exact versions in `requirements.txt`
- [ ] `safety check -r requirements.txt` passes with no known CVEs
- [ ] Dependency versions reviewed when adding new packages
- [ ] Safety scan runs automatically in CI on every push

## Network Security

- [ ] PostgreSQL port (5432) is NOT exposed to the host machine in production (internal Docker network only)
- [ ] Prometheus port (9090) is NOT publicly accessible without a reverse proxy + auth in production
- [ ] Grafana is behind authentication before any public exposure
- [ ] All Docker services communicate on an internal Docker network (`stock-net`)

## Data

- [ ] No PII (Personally Identifiable Information) is stored
- [ ] All data is sourced from a public API (no personal brokerage or account data)
- [ ] Database connection uses SSL in production (set `POSTGRES_SSLMODE=require`)

---

## Common Python Security Mistakes (what Bandit detects)

Understanding *why* these are dangerous helps you avoid them instinctively:

### 1. Hardcoded credentials
```python
# BAD — password is now in git forever if this is committed
db_password = "mypassword123"

# GOOD — loaded from environment at runtime
import os
db_password = os.environ["POSTGRES_PASSWORD"]
```

### 2. SQL Injection
```python
# BAD — an attacker can craft symbol to execute arbitrary SQL
symbol = "'; DROP TABLE stock_prices; --"
query = f"SELECT * FROM stock_prices WHERE symbol = '{symbol}'"

# GOOD — parameterized query, the DB driver escapes the value safely
query = "SELECT * FROM stock_prices WHERE symbol = :symbol"
session.execute(query, {"symbol": symbol})
```

### 3. Using `assert` as a security gate
```python
# BAD — Python strips assert statements when run with optimization flag (-O)
# So this check silently disappears in optimized/production mode
assert user_is_authenticated, "Not authorized"

# GOOD — use an explicit if statement
if not user_is_authenticated:
    raise PermissionError("Not authorized")
```

### 4. Insecure random numbers
```python
# BAD — random is predictable and not cryptographically secure
import random
token = random.randint(100000, 999999)

# GOOD — use the secrets module for anything security-related
import secrets
token = secrets.token_hex(16)
```

### 5. Deserializing untrusted data
```python
# BAD — pickle can execute arbitrary code during deserialization
import pickle
data = pickle.loads(untrusted_bytes)

# GOOD — use JSON for data exchange with untrusted sources
import json
data = json.loads(untrusted_string)
```

---

## OWASP Top 10 — Quick Reference

The Open Web Application Security Project publishes the 10 most critical web security risks.
These are the ones most relevant to this project:

| # | Risk | How We Mitigate It |
|---|------|--------------------|
| A01 | Broken Access Control | Grafana behind authentication; DB not publicly exposed |
| A02 | Cryptographic Failures | No sensitive data stored; HTTPS in production |
| A03 | Injection | Parameterized SQL queries throughout |
| A05 | Security Misconfiguration | No default credentials; all services configured via env vars |
| A06 | Vulnerable Components | `safety check` in CI catches known CVEs |
| A09 | Security Logging | Pipeline logs errors; Prometheus tracks error rates |

---

*Last reviewed: Phase 1 baseline*
*Next review: Before any production deployment*
