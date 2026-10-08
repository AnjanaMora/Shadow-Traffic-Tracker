# ⚡ Shadow Traffic

> **Proactive website traffic congestion prediction and mitigation platform.**  
> Forecasts server saturation, latency degradation, and capacity bottlenecks **before** customer-facing outages occur, backed by seasonal baselining, dual-model forecasting, cloud auto-remediation, and deployment root-cause correlation.

---

## 🏆 Headline Results

| Metric | Result | Benchmark Source |
|---|---|---|
| **Proactive Lead Time** | **`10.0 minutes`** before SLA outage | Verified in E2E harness (`tests/e2e/test_proactive_lead_time.py`) |
| **False Alarm Rate** | **`0.0%`** on 2.5x seasonal spikes | Verified in Scenario C (`prediction-engine/tests/`) |
| **Auto-Remediation Latency** | **`< 120 ms`** trigger time | Verified in `backend/tests/test_remediation.py` |
| **Root-Cause Attribution** | **`100%`** accuracy on deploy window | Correlated commit within $[-2\text{m}, +30\text{m}]$ lookback |

👉 Detailed benchmark numbers, charts, and test run logs are documented in **[RESULTS.md](RESULTS.md)**.

---

## 📁 Repository Structure

```text
shadow-traffic/
├── shared/                          # Canonical shared types, models & JSON schemas
│   ├── schema/                      # Canonical JSON Schema (metric_event.json)
│   ├── python/                      # Installable shared package (shadow_shared)
│   └── types/                       # TypeScript declarations (metric.d.ts)
├── collector/                       # Telemetry collection agent & traffic simulator (Python)
├── prediction-engine/               # Statistical + ML forecasting microservice (FastAPI)
├── backend/                         # Core API gateway, TimescaleDB, alerting & remediation (FastAPI)
├── dashboard/                       # Real-time telemetry operations console (React + Vite + Tailwind)
├── tests/                           # End-to-end integration and lead-time test harness
│   └── e2e/
│       └── test_proactive_lead_time.py  # Proof of 10-minute proactive lead time
├── docker-compose.yml               # Production orchestration with health checks
├── docker-compose.demo.yml          # Interactive demo orchestration with pre-scripted congestion
├── ARCHITECTURE.md                  # Comprehensive system architecture & data flow diagrams
├── RESULTS.md                       # Empirical test results, benchmarks & slide deck summary
├── DEPLOYMENT.md                    # VPS deployment guide, env configuration & runbook
└── README.md                        # Quickstart documentation
```

---

## ⚖️ Implementation Truth Table: Built vs. Planned (Real vs. Simulated)

To maintain complete engineering honesty and academic integrity, the following matrix outlines what is fully functional in production code vs. what is simulated or a stretch goal:

| Feature / Subsystem | Status | Real vs. Simulated | Details |
|---|---|---|---|
| **168-Hour Seasonal Baseline** | ✅ **Built** | **100% Real** | Full 7-day × 24-hour slot matrix with EWMA weekly decay and variance floors. Suppresses false alarms during predictable diurnal surges. |
| **Dual Forecaster (ARIMA + EWMA)** | ✅ **Built** | **100% Real** | Dual-track forecasting engine with polynomial trend regression, confidence intervals, and momentum tracking. |
| **Explainable Risk Scoring (SHAP-style)**| ✅ **Built** | **100% Real** | Weighted percentage attribution bar showing exact contribution of latency, request rate, errors, and users. |
| **TimescaleDB Time-Series Engine** | ✅ **Built** | **100% Real** | Hypertables with 1-day chunks, continuous rollups (`1m` & `5m`), retention policies, and idempotent deduplication. |
| **Multi-Tenant Mini-SaaS Management** | ✅ **Built (Stretch)** | **100% Real** | Account profiles, multi-site registration, custom thresholds, and scoped API key validation (`st_live_<hex>`). |
| **Root-Cause Correlation** | ✅ **Built (Stretch)** | **100% Real** | Deployment ledger correlating alerts against recent CI/CD deployments within a rolling time window. |
| **Closed-Loop Auto-Remediation** | ✅ **Built (Stretch)** | **Simulated Webhook** | Fully implemented webhook trigger and dashboard state reflecting $2 \to 4$ instance scale-out; calls a mock cloud provider API. |
| **Telemetry Collector** | ✅ **Built** | **Hybrid** | Features real Prometheus `/metrics` scraping and Nginx access log tailing, plus a synthetic simulation mode for demos. |
| **Live Web Console** | ✅ **Built** | **100% Real** | React 18 + Vite 5 + Tailwind CSS dashboard with WebSocket push streaming, Recharts baseline bands, and modals. |

---

## 🚀 Quickstart with Docker Compose

### Prerequisites
- [Docker Engine](https://docs.docker.com/engine/install/) (v24.0+)
- [Docker Compose](https://docs.docker.com/compose/install/) (v2.20+)

### 1. Launch the Complete Stack
```bash
# Clone the repository
cd "Shadow Traffic Manager"

# Launch all microservices in detached mode
docker compose up -d --build
```

### 2. Verify Services
```bash
docker compose ps
```

| Service | Endpoint | Purpose |
|---|---|---|
| **Dashboard UI** | [http://localhost:3000](http://localhost:3000) | Live operations console & charts |
| **Backend Gateway** | [http://localhost:8000/docs](http://localhost:8000/docs) | OpenAPI Swagger specification |
| **Backend Health** | [http://localhost:8000/health](http://localhost:8000/health) | TimescaleDB & Prediction connectivity |
| **Prediction Microservice** | [http://localhost:8001/docs](http://localhost:8001/docs) | Forecasting API docs |

---

## 🎬 Running the Live End-to-End Demo

To demonstrate the proactive warning capability live:

```bash
# Spin up demo stack with scripted congestion ramp
docker compose -f docker-compose.demo.yml up --build
```

Then execute the automated lead time verification:
```bash
python tests/e2e/test_proactive_lead_time.py
```
This script polls `/api/status/:site_id`, asserts that status elevates to `WARNING` with an ETA to congestion, and verifies that the warning occurs **10.0 minutes before** error rates cross the critical SLA boundary.

---

## 🧪 Running Automated Tests

Run the unit and integration test suites across all services:

```bash
# 1. Shared Contract Tests
pytest shared/python/tests -v

# 2. Prediction Engine Tests (11/11 passing)
pytest prediction-engine/tests -v

# 3. Backend Integration & Tenancy Tests (23/23 passing)
pytest backend/tests -v

# 4. Proactive Lead Time E2E Test (1/1 passing)
pytest tests/e2e/test_proactive_lead_time.py -v
```

---

## 📚 Deep Dive Documentation

For detailed information on individual modules and operational workflows, explore:
- **[ARCHITECTURE.md](ARCHITECTURE.md)**: System design, data flow diagrams, and tech stack justifications.
- **[RESULTS.md](RESULTS.md)**: Detailed test numbers, false-alarm analysis, and presentation slides.
- **[DEPLOYMENT.md](DEPLOYMENT.md)**: VPS production deployment, CI/CD pipeline, and observability guidelines.
- **[collector/README.md](collector/README.md)**: Collector agent operational modes (simulation, Prometheus, logs).
- **[prediction-engine/README.md](prediction-engine/README.md)**: Baseline matrix, dual forecaster, and risk scoring.
- **[backend/README.md](backend/README.md)**: FastAPI gateway, TimescaleDB DAL, tenancy, and auto-remediation.
- **[dashboard/README.md](dashboard/README.md)**: React/Vite architecture, WebSocket streaming, and Recharts baselines.
