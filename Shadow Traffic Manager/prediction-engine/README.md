# 🧠 Prediction Engine Module (`prediction-engine/`)

> High-throughput statistical and machine learning microservice for seasonal baselining, time-series forecasting, and explainable congestion scoring.

---

## 1. Overview & Architecture

The Prediction Engine operates as an independent microservice exposing REST APIs (`FastAPI`). It performs four mathematical pipelines on incoming telemetry:

1. **168-Hour Seasonal Baseline Matrix (`src/baseline.py`)**:
   Tracks moving mean ($\mu$) and standard deviation ($\sigma$) for every hour of the week ($7 \times 24 = 168$ discrete slots). Employs EWMA decay ($\beta=0.15$) to smoothly adapt to organic weekly traffic shifts while suppressing false alarms during expected peak hours.
2. **Dual-Model Forecaster (`src/forecaster.py`)**:
   Combines short-term exponential velocity (EWMA momentum) with multi-step polynomial/Auto-ARIMA trend extrapolation to forecast traffic $15$ minutes ahead with $95\%$ confidence bounds.
3. **Multi-Factor Risk Scorer (`src/risk_scorer.py`)**:
   Synthesizes request velocity, latency drift, error rate anomalies, and active user volume into a composite risk score ($0 - 100$).
4. **SHAP-Style Attribution & ETA Extrapolator (`src/risk_scorer.py`)**:
   Decomposes the composite risk into percentage attributions (e.g. Response Time: $45\%$, Request Rate: $30\%$) and projects time-to-congestion (ETA minutes) before SLA boundaries are breached.

---

## 2. Running in Isolation

### Prerequisites
- Python 3.10+ (tested on Python 3.14)

### Installation
```bash
# Install shared contracts
pip install -e ../shared/python

# Install prediction engine dependencies
cd prediction-engine
pip install -r requirements.txt
```

### Starting the Microservice
```bash
uvicorn src.main:app --host 0.0.0.0 --port 8001 --reload
```

### Interactive API Documentation
Once running, navigate to:
- **Swagger UI**: [http://localhost:8001/docs](http://localhost:8001/docs)
- **ReDoc**: [http://localhost:8001/redoc](http://localhost:8001/redoc)
- **Health Check**: [http://localhost:8001/health](http://localhost:8001/health)

---

## 3. Running Unit & Integration Tests

```bash
pytest tests/ -v
```

### What the Test Suite Verifies (11/11 Passing)
- `test_baseline.py`: Time slot isolation (Monday 09:00 vs Sunday 03:00), exponential weekly weighting, and variance floor safeguards.
- `test_forecaster.py`: Trajectory forecast confidence intervals, short series handling, and momentum dampening.
- `test_risk_scorer.py`: Multi-factor weight justifications, ETA calculations, and sanity caps.
- `test_scenarios.py`:
  - **Scenario A**: Normal traffic stays in low score regime ($0 - 30$).
  - **Scenario B**: Gradual congestion ramps generate a `WARNING` state with $\ge 10\text{ minutes}$ lead time.
  - **Scenario C**: 2.5x traffic surge matching Monday 14:00 historical baseline is suppressed (0% false alarms).
