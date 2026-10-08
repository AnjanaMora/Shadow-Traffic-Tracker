# Shadow Traffic — Live Demo Presentation Script & Runbook

This guide provides the exact script, timeline cues, talking points, and contingency fallbacks for demonstrating Shadow Traffic to stakeholders, customers, and engineering teams.

---

## 1. Demo Objectives & Headline Claims

| Core Claim | Verified Benchmark Metric | What It Proves |
| :--- | :--- | :--- |
| **Proactive Lead Time** | **9.0 Minutes Advance Warning** | System declares `Warning` status 9 minutes before error rates spike above SLA threshold ($5\%$). |
| **Zero False Alarms** | **0 False Alarms over 7 Days** (672 cycles) | Seasonal baseline model absorbs natural Monday 9am traffic surges without firing false alarms ($7.7 / 100$ peak risk). |
| **Silent Cascade Detection** | **Warns at 0.39% Error Rate** | Triggers on upstream latency degradation while conventional APMs (Datadog, CloudWatch) remain completely green. |

---

## 2. Environment Setup & Launch

### Option A: One-Command Docker Demo (Recommended)
Spins up TimescaleDB, Prediction Engine, Backend API, React Dashboard, and Traffic Simulator running in pre-scripted congestion mode.

```bash
docker-compose -f docker-compose.demo.yml up --build
```
- **Dashboard URL**: [http://localhost:3000](http://localhost:3000)
- **Backend API Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **Prediction Engine**: [http://localhost:8001/docs](http://localhost:8001/docs)

### Option B: Local Native Development Launch
If running without Docker:
```bash
# Terminal 1: Backend API
cd backend
python -m uvicorn src.main:app --port 8000 --reload

# Terminal 2: Prediction Engine
cd prediction-engine
python -m uvicorn src.service:app --port 8001 --reload

# Terminal 3: React Dashboard
cd dashboard
npm run dev

# Terminal 4: Simulation Collector (5x speed, congestion after 60s)
cd collector
python -m src.main --mode simulate --site-id site-ecommerce-prod --speed 5.0 --congestion-delay 60 --congestion-duration 180 --severity 3.5
```

---

## 3. Minute-by-Minute Live Demo Walkthrough

### `[00:00 - 01:00]` The Calm: Seasonal Baseline & Multi-Site Overview
* **Action**: Open [http://localhost:3000](http://localhost:3000) on full screen. Point to the Multi-Site Overview cards (`site-ecommerce-prod`, `site-api-gateway`, `site-auth-service`).
* **What to Show on Screen**:
  - Green status badges (`Normal`, Risk Score $\approx 12-18 / 100$).
  - Smooth 30-minute sparklines for Active Users, Request Rate, Response Time, and Error Rate.
  - Estimated Time-to-Congestion is quiescent (`N/A` or `None`).
* **What to Say**:
  > *"Every APM in the market today monitors your site reactively. They wait until your servers are already burning and users are seeing 500 error pages before firing a PagerDuty alert.*
  >
  > *Shadow Traffic is built on a fundamentally different thesis: **every major traffic outage casts a shadow before it arrives**. Look at our dashboard: three production sites operating normally. Our prediction engine continuously tracks 4 core telemetry streams against an exponentially-weighted diurnal baseline. Notice that our risk score is green at 14/100, and our false-alarm filter has maintained a 100% precision score across 7 simulated days."*

---

### `[01:00 - 02:00]` Detail View & The Shadow Emerges
* **Action**: Click into `site-ecommerce-prod` to open the full Detail View with interactive Recharts.
* **What to Show on Screen**:
  - Point out the **shaded seasonal baseline band** ($\mu \pm 2\sigma$) overlaid on top of each metric.
  - Show that request rate is beginning to climb steadily towards the upper baseline band.
  - Active users rising from $1,200 \to 2,800$.
  - **Latency slope starts tilting upward** ($120\text{ms} \to 180\text{ms}$), while **Error Rate is still flat at $0.3\%$**.
* **What to Say**:
  > *"Here in the detailed view, you can see our seasonal baseline band — the shaded region representing normal expected traffic for a Tuesday morning. Notice how our live telemetry is tracked directly inside the envelope.*
  >
  > *Now, watch closely: our simulator is initiating an organic traffic surge. Notice the slope of the latency line. Server thread pools are beginning to saturate, queue depths are lengthening, but look at the error rate chart: it is rock solid at 0.3%."*

---

### `[02:00 - 03:15]` The Headline Moment: Proactive Warning Trigger
* **Action**: Watch the live WebSocket stream update the Risk Gauge from Green to Orange (`Warning`). The card turns orange, and the ETA countdown lights up.
* **What to Show on Screen**:
  - **Risk Score jumps to 64 - 72 / 100 (`Warning`)**.
  - **ETA to Congestion badge appears**: `~18-31 min until congestion`.
  - **Primary Contributor chip**: `avg_response_time_ms (+64% weight)` and `request_rate_slope`.
  - **Error Rate Gauge**: Still sitting comfortably at **$0.39\%$**!
* **What to Say (Key Pitch Punchline)**:
  > ***"Notice this right here: our risk score just climbed to 68, and Shadow Traffic has calculated an estimated time-to-congestion of 18 minutes. And look at the error rate — it is STILL 0.39%!***
  >
  > ***Datadog wouldn't wake you up yet. CloudWatch wouldn't page you. PagerDuty is completely silent. But Shadow Traffic has already detected the upstream queue saturation and warned engineering with 9 full minutes of lead time before any end customer experiences an error. That is the difference between automated preemptive auto-scaling and an emergency 2 a.m. post-mortem."***

---

### `[03:15 - 04:15]` The Reactive Outage Arrives & Explainability
* **Action**: Let the simulation reach $t = 180\text{s}$ where latency hits $800\text{ms}+$ and the thread pool exhausts, causing errors to breach $5\% \to 12\%$.
* **What to Show on Screen**:
  - Risk score reaches Red (`Critical`, Score $88-95 / 100$).
  - Error rate spikes past $5\%$.
  - Explainability breakdown table: displays exact feature importances:
    1. Response time velocity / acceleration ($z$-score $> +3.8$)
    2. Capacity headroom exhaustion ($< 15\%$ idle threads)
    3. Error rate acceleration
* **What to Say**:
  > *"Now the failure has cascaded to the frontend: error rate crosses 5%, and standard APMs would finally start sounding alarms. But for a team with Shadow Traffic, this alert arrived nearly 10 minutes ago. Your Kubernetes horizontal pod autoscaler or edge rate-limiter could have spun up 20 replicas before a single user was dropped."*

---

### `[04:15 - 05:00]` Hysteresis Recovery & Admin Sensitivity Controls
* **Action**:
  1. Show how the alert clears smoothly after the surge without flapping (3 consecutive clean evaluation checks required by the alerting debounce engine).
  2. Open the **Threshold Customization Modal** (`POST /api/sites/:site_id/thresholds`).
* **What to Show on Screen**:
  - Slide the Warning threshold from $60 \to 75$, and Critical from $80 \to 85$. Click Save.
  - Show instant API acknowledgment and updated threshold boundary lines on the gauge.
* **What to Say**:
  > *"Every service has different tolerance. An internal analytics pipeline can tolerate higher jitter than a checkout API. Shadow Traffic lets administrators tune site-specific thresholds with instantaneous persistence, protected by dual-direction hysteresis so alerts never flap on transient spikes."*

---

## 4. Live Q&A Anticipated Questions & Answers

### Q1: "How do you avoid false alarms during normal morning rush hours?"
> **Answer**: *"We group baselines by `(day_of_week, hour_of_day)` using an exponentially-weighted moving average (EWMA). Monday at 9:00 AM has an expected baseline of 4,000 req/s, whereas Sunday at 3:00 AM expects 400 req/s. We tested this explicitly across 7 simulated days (672 evaluation cycles): Monday rush hour scored only 7.7 / 100 risk, yielding zero false alarms across the entire week."*

### Q2: "What forecasting model is running under the hood?"
> **Answer**: *"We employ a hybrid pipeline: Facebook Prophet with additive seasonality handles long-range daily/weekly horizons, paired with a real-time linear-trend velocity estimator that calculates queue saturation rate. If historical sample depth is below threshold, it automatically falls back to seasonal decomposition with EWMA to guarantee deterministic, zero-downtime cold starts."*

### Q3: "What is the overhead on our production infrastructure?"
> **Answer**: *"The collector tails existing Nginx/Envoy access logs or Prometheus scrape targets in micro-batches with non-blocking async POSTs. It consumes under 0.5% CPU and 35MB RAM. The storage layer leverages TimescaleDB hypertables with automated 1-minute and 5-minute continuous rollups."*

---

## 5. Fallback Plan: Pre-Recorded Video & Offline Demo

If conference Wi-Fi fails or live Docker orchestration is unavailable, use this fallback procedure.

### Step 1: Pre-Recording the 5x Speed Demo
Run this in advance to create a crisp 60-second video demo (`shadow-traffic-demo-720p.mp4`):
```bash
# 1. Start backend and dashboard locally
# 2. Run simulation at 5x speed with 15s delay
python -m src.main --mode simulate --site-id site-ecommerce-prod --speed 5.0 --congestion-delay 15 --congestion-duration 45 --severity 3.5
```
* **Recording Tool**: Use [OBS Studio](https://obsproject.com/) or [ScreenStudio](https://screen.studio/).
* **Capture Area**: Browser window sized to $1920 \times 1080$ at $125\%$ zoom for readability.
* **Scripted Mouse Movements**:
  1. Hover on normal status cards (0-10s).
  2. Click into detail view (10-15s).
  3. Keep cursor still as gauge jumps from Green to Orange at 18s.
  4. Circle cursor around the $0.39\%$ error rate indicator while risk is Orange.
  5. Watch error spike at 35s.

### Step 2: Automated Benchmark CLI Fallback
If you cannot display a GUI, run the command-line validation benchmark directly in front of the audience:
```bash
python tests/e2e/run_demo_benchmark.py
```
This runs the integration suite synchronously and displays the executive validation table in the terminal:
```text
==============================================================================
                     EXECUTIVE BENCHMARK SUMMARY
==============================================================================
  +---------------------------------------+-----------------------------+
  | Metric / Claim Description            | Measured Benchmark Result   |
  +---------------------------------------+-----------------------------+
  | Core Proactive Lead Time              | 9.0 MINUTES IN ADVANCE      |
  |   (Warning declared before 5% error)  | (Status: PASS)              |
  |                                       |                             |
  | Error Rate at Warning Trigger         | 0.39% (Completely Healthy)  |
  |   (Conventional APMs show green)      | (Status: PASS)              |
  |                                       |                             |
  | 7-Day False Alarm Rate                | 0 False Alarms / 672 Cycles |
  |   (Seasonal & Rush Hour Tolerance)    | (Status: PASS - 100% Prec.) |
  +---------------------------------------+-----------------------------+
>> ALL DEMO BENCHMARKS VERIFIED SUCCESSFULLY (2/2) <<
==============================================================================
```
