"""
Shadow Traffic — End-to-End Proactive Lead-Time Test
=====================================================
The single most important test in the project:
Proves the core architectural claim: "Proactive, Not Reactive".

Workflow:
1. Calibrates normal diurnal baseline (latency ~38ms, errors < 0.25%, RPS ~400).
2. Initiates simulated congestion ramp.
3. Asserts that the system triggers 'Warning' with eta_minutes > 0
   BEFORE user-facing error rates spike.
4. Asserts error rate is healthy (< 2.0%) at the exact moment Warning is declared.
5. Advances until the error rate breaches the critical SLA failure threshold (>= 5.0%).
6. Measures and records the exact proactive lead time achieved.
"""

import sys
import types
from pathlib import Path
from datetime import datetime, timezone, timedelta
import pytest
from fastapi.testclient import TestClient

# Ensure all monorepo source packages are in sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "shared" / "python"))
sys.path.insert(0, str(REPO_ROOT / "collector"))
sys.path.insert(0, str(REPO_ROOT / "backend"))

# Register prediction-engine cleanly under "prediction_engine" to avoid "src" collision
pe_root = REPO_ROOT / "prediction-engine" / "src"
if "prediction_engine" not in sys.modules:
    pkg = types.ModuleType("prediction_engine")
    pkg.__path__ = [str(pe_root)]
    pkg.__file__ = str(pe_root / "__init__.py")
    sys.modules["prediction_engine"] = pkg

from prediction_engine.service import assess_risk as pe_assess_risk
from shadow_shared.models import MetricEvent, CongestionLevel
from collector.src.simulator import TrafficSimulator
from backend.src.main import app, latest_assessments, active_sites
from backend.src.storage import dal


@pytest.fixture
def api_client():
    with TestClient(app) as c:
        yield c


def test_proactive_congestion_warning_lead_time(api_client):
    """
    Asserts:
    1. System transitions from Normal to Warning before error rate spikes.
    2. At warning declaration, eta_minutes > 0.
    3. At warning declaration, error_rate_percent is strictly < 2.0% (healthy).
    4. Records lead time (minutes between Warning trigger and error spike >= 5.0%).
    """
    site_id = "test-lead-time-ecommerce"
    api_key = "shadow-dev-key-123"

    # Virtual time: 30-minute congestion ramp
    # In virtual time, step is 30s per tick
    step_seconds = 30.0
    congestion_delay = 300.0        # 5 mins baseline
    congestion_duration = 1800.0    # 30 mins ramp

    start_time = datetime(2026, 9, 21, 10, 0, 0, tzinfo=timezone.utc)
    simulator = TrafficSimulator(
        site_id=site_id,
        base_users=1400,
        noise_percent=4.0,
        speed_multiplier=1.0,
        congestion_delay_seconds=congestion_delay,
        congestion_duration_seconds=congestion_duration,
        congestion_severity=3.8,
        start_time=start_time,
    )

    # -------------------------------------------------------------------------
    # 1. Warm-up Phase: Establish healthy seasonal baseline
    # -------------------------------------------------------------------------
    baseline_events = []
    curr_time = start_time - timedelta(hours=3)
    for _ in range(30):
        curr_time += timedelta(minutes=6)
        ev = MetricEvent(
            site_id=site_id,
            timestamp=curr_time,
            active_users=1400,
            request_rate=450.0,
            avg_response_time_ms=38.5,
            error_rate_percent=0.15,
        )
        baseline_events.append(ev)

    # Warm up baseline model with historical data
    pe_assess_risk(site_id=site_id, current_window=baseline_events, historical_data=baseline_events)

    # In-memory tracking variables
    warning_declared = False
    warning_timestamp = None
    warning_eta_minutes = None
    warning_error_rate = None
    warning_latency = None

    spike_timestamp = None
    spike_error_rate = None

    history_buffer = list(baseline_events)

    from backend.src.security.rate_limiter import rate_limiter
    rate_limiter.max_requests = 10000
    rate_limiter.reset()

    # -------------------------------------------------------------------------
    # 2. Simulation Loop: Advance through baseline and congestion ramp
    # -------------------------------------------------------------------------
    max_steps = 70  # ~35 virtual minutes
    for step in range(max_steps):
        metric = simulator.generate_next_metric(step_seconds=step_seconds)
        history_buffer.append(metric)
        if len(history_buffer) > 60:
            history_buffer.pop(0)

        # Ingest metric into backend API gateway
        res_post = api_client.post(
            "/api/metrics",
            json=metric.model_dump(mode="json"),
            headers={"X-API-Key": api_key},
        )
        assert res_post.status_code == 201

        # Run risk assessment pipeline on current window
        assessment = pe_assess_risk(
            site_id=site_id,
            current_window=history_buffer[-30:],
        )
        # Store assessment so GET /api/status/{site_id} returns it
        latest_assessments[site_id] = assessment.model_dump(mode="json")

        # Poll status endpoint
        res_status = api_client.get(f"/api/status/{site_id}")
        assert res_status.status_code == 200
        status_data = res_status.json()

        curr_score = status_data["current_risk_score"]
        curr_status = status_data["status"]
        curr_eta = status_data["eta_minutes"]

        # Check if Warning status reached with an active positive ETA
        if not warning_declared and curr_status in ["Warning", "Critical"] and curr_eta is not None and curr_eta > 0.0:
            warning_declared = True
            warning_timestamp = metric.timestamp
            warning_eta_minutes = curr_eta
            warning_error_rate = metric.error_rate_percent
            warning_latency = metric.avg_response_time_ms

        # Check if user-facing error rate breached critical SLA threshold (>= 5.0%)
        if warning_declared and spike_timestamp is None and metric.error_rate_percent >= 5.0:
            spike_timestamp = metric.timestamp
            spike_error_rate = metric.error_rate_percent
            break

    # -------------------------------------------------------------------------
    # 3. Core Claims Assertions
    # -------------------------------------------------------------------------
    # Claim 1: Warning status MUST be reached
    assert warning_declared, "System failed to transition to Warning status during congestion ramp!"

    # Claim 2: ETA to congestion must be populated and non-zero
    assert warning_eta_minutes is not None, "Warning status must provide an estimated time-to-congestion (eta_minutes)!"
    assert warning_eta_minutes > 0.0, f"eta_minutes must be > 0, got {warning_eta_minutes}"

    # Claim 3: Error rate at warning declaration must be healthy (< 2.0%)
    # This is the literal proof of proactivity: we warned while error rates were still nominal!
    assert warning_error_rate < 2.0, (
        f"Proactivity violation! Warning triggered too late: error rate was already {warning_error_rate}% "
        f"(expected < 2.0% healthy baseline)"
    )

    # Claim 4: Error spike must occur later, proving positive lead time
    assert spike_timestamp is not None, "Simulation ended before error rate breached SLA threshold (5.0%)"
    assert spike_timestamp > warning_timestamp, "Error spike must occur AFTER warning declaration!"

    # Calculate actual lead time achieved
    lead_time_seconds = (spike_timestamp - warning_timestamp).total_seconds()
    lead_time_minutes = lead_time_seconds / 60.0

    print("\n" + "=" * 70)
    print("[PROACTIVE DEMO] CONGESTION WARNING -- END-TO-END VERIFICATION")
    print("=" * 70)
    print(f"Target Monitored Site        : {site_id}")
    print(f"Warning Declaration Time     : {warning_timestamp.isoformat()}")
    print(f"Latency at Warning           : {warning_latency:.1f} ms")
    print(f"Error Rate at Warning        : {warning_error_rate:.2f}% (HEALTHY)")
    print(f"Reported ETA to Congestion   : ~{warning_eta_minutes:.1f} minutes")
    print("-" * 70)
    print(f"SLA Breach Failure Time      : {spike_timestamp.isoformat()}")
    print(f"Peak Error Rate at Breach    : {spike_error_rate:.2f}% (5xx SATURATION)")
    print("=" * 70)
    print(f">> HEADLINE METRIC: Warned {lead_time_minutes:.1f} minutes before service degradation! <<")
    print("=" * 70 + "\n")

    # Assert at least 5 minutes of lead time
    assert lead_time_minutes >= 5.0, (
        f"Insufficient lead time: {lead_time_minutes:.1f} minutes (expected >= 5.0 minutes)"
    )


if __name__ == "__main__":
    pytest.main(["-s", "-v", __file__])
