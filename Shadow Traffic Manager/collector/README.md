# 📡 Collector Module (`collector/`)

> Edge telemetry ingestion agent and traffic simulation suite for Shadow Traffic.

---

## 1. Overview & Operational Modes

The collector agent bridges monitored systems and the Shadow Traffic backend gateway. It operates in three distinct modes:

1. **Simulation Mode (`simulator.py`)**:
   Generates synthetic diurnal web traffic (diurnal sinusoidal curves, lunch-hour surges, realistic Gaussian jitter, and scheduled congestion ramps) for end-to-end testing without needing a live production website.
2. **Prometheus Scraper Mode (`prometheus_scraper.py`)**:
   Scrapes standard Prometheus `/metrics` endpoints, extracting active requests, rate per second, and error distributions.
3. **Log Tailer Mode (`log_tailer.py`)**:
   Tails and parses standard Nginx, Apache, or custom JSON access logs in real time, computing sliding-window rates.

All modes validate and dispatch canonical `MetricEvent` objects to the backend using `X-API-Key` authentication.

---

## 2. Running in Isolation

### Prerequisites
- Python 3.10+ (tested on Python 3.14)
- Virtual environment recommended

### Installation
From the repository root or `collector/` directory:
```bash
# Install the shared contract package first
pip install -e ../shared/python

# Install collector dependencies
pip install -r requirements.txt
```

### Execution Options

#### Option A: Run Synthetic Traffic Simulation (Default Demo)
```bash
# Point to local or remote backend
export BACKEND_URL="http://localhost:8000"
export SITE_ID="store-frontend-prod"
export API_KEY="st_live_store_demo_key"
export EMIT_INTERVAL_SEC="3.0"

python -m src.agent
```

#### Option B: Run Scripted Congestion Ramp (For E2E Lead-Time Verification)
```bash
python -m src.agent --mode ramp --ramp-start-minute 5 --ramp-peak-minute 15
```

#### Option C: Run Prometheus Scraper
```bash
export COLLECTOR_MODE="prometheus"
export PROMETHEUS_URL="http://your-app:9090/metrics"
python -m src.agent
```

---

## 3. Running Unit & Integration Tests

```bash
pytest tests/ -v
```

### Test Coverage Highlights
- `test_simulator.py`: Verifies diurnal traffic generation, diurnal hour weighting, and congestion ramp profiles.
- `test_agent.py`: Verifies HTTP payload formatting, header generation (`X-API-Key`), retry handling, and backoff.
