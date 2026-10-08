"""
Shadow Traffic — Gateway & Alerting Integration Tests
Role in Architecture:
    Tests end-to-end Gateway security, API key auth, per-site rate limiting,
    dynamic threshold tuning, status querying, and the hysteresis-based alert
    debouncing engine (verifying alerts fire exactly once on confirmed transitions).
"""

import asyncio
from datetime import datetime, timezone, timedelta
import pytest
from fastapi.testclient import TestClient

from shadow_shared.models import MetricEvent, CongestionLevel
from src.main import app, alerting_engine, active_sites
from src.alerting.engine import AlertingEngine
from src.security.rate_limiter import rate_limiter


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def _sample_metric_payload(site_id: str, offset_mins: int = 0, rps: float = 100.0, latency: float = 40.0, errors: float = 0.1):
    return {
        "site_id": site_id,
        "timestamp": (datetime.now(timezone.utc) - timedelta(minutes=offset_mins)).isoformat(),
        "active_users": int(rps * 3),
        "request_rate": rps,
        "avg_response_time_ms": latency,
        "error_rate_percent": errors,
    }


def test_api_key_authentication(client):
    payload = _sample_metric_payload("auth-test-site")

    # 1. Missing API key header -> 401 Unauthorized
    res_missing = client.post("/api/metrics", json=payload)
    assert res_missing.status_code == 401
    assert "X-API-Key" in res_missing.json()["detail"]

    # 2. Invalid API key header -> 401 Unauthorized
    res_invalid = client.post(
        "/api/metrics",
        json=payload,
        headers={"X-API-Key": "completely-invalid-key"},
    )
    assert res_invalid.status_code == 401

    # 3. Valid API key header -> 201 Created
    res_valid = client.post(
        "/api/metrics",
        json=payload,
        headers={"X-API-Key": "shadow-dev-key-123"},
    )
    assert res_valid.status_code == 201
    assert res_valid.json()["status"] == "accepted"


def test_per_site_rate_limiting(client):
    site = "rate-limit-test-site"
    rate_limiter.reset(site)
    headers = {"X-API-Key": "shadow-dev-key-123"}
    payload = _sample_metric_payload(site)

    # Set artificial tight rate limit for test
    rate_limiter.max_requests = 5

    # First 5 requests should succeed
    for _ in range(5):
        res = client.post("/api/metrics", json=payload, headers=headers)
        assert res.status_code == 201

    # 6th request should be rate-limited (HTTP 429)
    res_overflow = client.post("/api/metrics", json=payload, headers=headers)
    assert res_overflow.status_code == 429
    assert "Retry-After" in res_overflow.headers

    # Reset rate limit
    rate_limiter.max_requests = 60
    rate_limiter.reset(site)


def test_site_thresholds_customization(client):
    site = "custom-threshold-site"

    # 1. Invalid thresholds (warning >= critical) -> 400 Bad Request
    bad_req = client.post(
        f"/api/sites/{site}/thresholds",
        json={"warning_threshold": 80.0, "critical_threshold": 70.0},
    )
    assert bad_req.status_code == 400

    # 2. Valid thresholds -> 200 OK
    good_req = client.post(
        f"/api/sites/{site}/thresholds",
        json={"warning_threshold": 50.0, "critical_threshold": 75.0},
    )
    assert good_req.status_code == 200
    data = good_req.json()
    assert data["warning_threshold"] == 50.0
    assert data["critical_threshold"] == 75.0

    # Verify alerting engine respects custom thresholds
    warn_t, crit_t = alerting_engine.get_site_thresholds(site)
    assert warn_t == 50.0
    assert crit_t == 75.0


def test_site_status_and_sites_overview(client):
    site = "overview-test-site"
    headers = {"X-API-Key": "shadow-dev-key-123"}

    # Ingest 2 metrics
    client.post("/api/metrics", json=_sample_metric_payload(site, offset_mins=5), headers=headers)
    client.post("/api/metrics", json=_sample_metric_payload(site, offset_mins=1), headers=headers)

    # Query /api/status/{site_id}
    res_status = client.get(f"/api/status/{site}")
    assert res_status.status_code == 200
    status_data = res_status.json()
    assert status_data["site_id"] == site
    assert "recent_metrics_30m" in status_data
    assert len(status_data["recent_metrics_30m"]) >= 2

    # Query /api/sites
    res_sites = client.get("/api/sites")
    assert res_sites.status_code == 200
    sites_list = res_sites.json()
    matching = [s for s in sites_list if s["site_id"] == site]
    assert len(matching) == 1
    assert matching[0]["site_id"] == site


def test_hysteresis_debouncing_alert_fires_exactly_once():
    """
    Simulates a congestion ramp-up through the AlertingEngine:
    1. Normal checks (score 20) -> 0 alerts
    2. Score jumps to Warning (score 65) for 1 check -> 0 alerts (debounced!)
    3. Score stays in Warning (score 68) for 2nd check -> EXACTLY 1 WARNING ALERT FIRES!
    4. Score stays in Warning (score 72) for 3rd check -> 0 alerts (suppressed, anti-flapping!)
    5. Score jumps to Critical (score 88) for 1 check -> 0 alerts (debounced!)
    6. Score stays in Critical (score 92) for 2nd check -> EXACTLY 1 CRITICAL ALERT FIRES!
    7. Score stays in Critical (score 95) for 3rd check -> 0 alerts (suppressed!)
    """
    async def _test():
        engine = AlertingEngine(required_consecutive_checks=2)
        site = "ramp-debouncing-site"

        fired_alerts = []

        now = datetime.now(timezone.utc)

        def _metric(score_hint: float) -> MetricEvent:
            return MetricEvent(
                site_id=site,
                timestamp=now,
                active_users=1000,
                request_rate=300.0,
                avg_response_time_ms=50.0 + (score_hint * 5.0),
                error_rate_percent=score_hint * 0.05,
            )

        # Step 1 & 2: Normal traffic (score 15.0)
        a1 = await engine.evaluate_metric_and_risk(_metric(15.0), risk_score=15.0)
        a2 = await engine.evaluate_metric_and_risk(_metric(15.0), risk_score=15.0)
        assert a1 is None
        assert a2 is None

        # Step 3: Enters Warning (score 65.0) - Check 1
        # MUST NOT fire alert yet because consecutive_pending_checks = 1 (< 2 required)
        a3 = await engine.evaluate_metric_and_risk(_metric(65.0), risk_score=65.0)
        assert a3 is None, "Alert fired prematurely on 1st check! Debouncing failed."

        # Step 4: Stays in Warning (score 68.0) - Check 2
        # MUST FIRE ALERT NOW!
        a4 = await engine.evaluate_metric_and_risk(_metric(68.0), risk_score=68.0)
        assert a4 is not None, "Alert failed to fire on 2nd consecutive check!"
        assert a4.level == CongestionLevel.HIGH  # Warning maps to HIGH
        fired_alerts.append(a4)

        # Step 5: Stays in Warning (score 72.0) - Check 3
        # MUST NOT fire a duplicate alert
        a5 = await engine.evaluate_metric_and_risk(_metric(72.0), risk_score=72.0)
        assert a5 is None, "Duplicate alert fired while hovering in Warning state!"

        # Step 6: Jumps to Critical (score 88.0) - Check 1
        # MUST NOT fire alert yet (requires 2 checks in Critical)
        a6 = await engine.evaluate_metric_and_risk(_metric(88.0), risk_score=88.0)
        assert a6 is None, "Critical alert fired prematurely on 1st check!"

        # Step 7: Stays in Critical (score 92.0) - Check 2
        # MUST FIRE CRITICAL ALERT NOW!
        a7 = await engine.evaluate_metric_and_risk(_metric(92.0), risk_score=92.0)
        assert a7 is not None, "Critical alert failed to fire on 2nd consecutive check!"
        assert a7.level == CongestionLevel.CRITICAL
        fired_alerts.append(a7)

        # Step 8: Stays in Critical (score 95.0) - Check 3
        # MUST NOT fire duplicate
        a8 = await engine.evaluate_metric_and_risk(_metric(95.0), risk_score=95.0)
        assert a8 is None, "Duplicate alert fired while hovering in Critical state!"

        # Assert total alert count is EXACTLY 2 (one Warning, one Critical)
        assert len(fired_alerts) == 2
        assert fired_alerts[0].level == CongestionLevel.HIGH
        assert fired_alerts[1].level == CongestionLevel.CRITICAL

    asyncio.run(_test())
