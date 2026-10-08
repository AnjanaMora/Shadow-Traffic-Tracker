# 🛡️ Backend API Gateway & Storage (`backend/`)

> Production-ready FastAPI API Gateway, TimescaleDB data access layer, multi-tenant manager, alerting engine, cloud auto-remediation, and deployment root-cause correlator.

---

## 1. Responsibilities & Subsystems

The backend microservice handles end-to-end data ingestion, persistence, tenancy, and automated response actions:

1. **API Gateway & Telemetry Ingestion (`src/main.py`)**:
   - `POST /api/metrics`: Ingests canonical `MetricEvent` telemetry.
   - `X-API-Key` scoped authentication: Validates site ownership and enforces rate limits.
   - Live WebSocket streaming: Dispatches live envelopes at `/ws/traffic`.
2. **TimescaleDB Data Access Layer (`src/storage/dal.py`)**:
   - Hypertables partitioned by timestamp into 1-day chunks.
   - Idempotent deduplication via composite key `(site_id, timestamp)`.
   - Continuous rollups: `metrics_1m_rollup` and `metrics_5m_rollup`.
3. **Multi-Tenant Mini-SaaS Management (`src/tenancy/`)**:
   - Multi-site registration (`POST /api/sites`), site updates, and deregistration.
   - Scoped API key generation (`st_live_<hex>`).
   - Tenant profile inspection (`GET /api/account`).
4. **Alerting & Notification Engine (`src/alerting/engine.py`)**:
   - Hysteresis debouncing (requires consecutive checks before state elevation).
   - Cooldown period enforcement per site to prevent notification storms.
   - Asynchronous webhook dispatch.
5. **Closed-Loop Auto-Remediation (`src/remediation/auto_scaler.py`)**:
   - Automatically calls mock cloud provider auto-scale webhooks upon Critical score breaches.
   - Tracks scaling status ($2 \to 4\text{ instances}$) and remediation audit history.
6. **Root-Cause Correlation Engine (`src/correlation.py`, `src/events.py`)**:
   - Records CI/CD deployments (`POST /api/deployments`).
   - Automatically cross-references alert timestamps against deployments in a $[-2\text{m}, +30\text{m}]$ window, surfacing actionable hypotheses.

---

## 2. Running in Isolation

### Prerequisites
- Python 3.10+ (tested on Python 3.14)
- TimescaleDB / PostgreSQL running (or run in in-memory / mock storage mode for local unit tests)

### Environment Variables
```bash
export DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:5432/shadow_traffic"
export PREDICTION_ENGINE_URL="http://localhost:8001"
export ENVIRONMENT="development"
export CORS_ORIGINS="http://localhost:3000"
```

### Installation
```bash
# Install shared contracts
pip install -e ../shared/python

# Install backend dependencies
cd backend
pip install -r requirements.txt
```

### Starting the Server
```bash
uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload
```

Interactive API documentation will be available at:
- **Swagger Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **Health Check**: [http://localhost:8000/health](http://localhost:8000/health)

---

## 3. Running Unit & Integration Tests

```bash
pytest tests/ -v
```

### What the Test Suite Verifies (23/23 Passing)
- `test_backend.py`: Health check, valid/invalid metric ingestion, alert manager cooldowns.
- `test_gateway_integration.py`: API key authentication, per-site rate limiting, custom thresholds, hysteresis debouncing.
- `test_storage.py`: Hypertable insert idempotency on duplicate timestamps, time-window filtering, seasonal lookbacks.
- `test_tenancy.py`: Tenant account profiles, site registration, API key isolation, CRUD operations.
- `test_remediation.py`: Auto-scaler trigger on Critical score, instance scaling, remediation logs.
- `test_correlation.py`: Deployment event recording and automated correlation hypothesis tagging on alerts.
