import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from shadow_shared.models import MetricEvent, CongestionLevel, TrafficPrediction
from src.main import app
from src.alerting import AlertManager


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_health_check_endpoint(client):
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert "status" in data
    assert data["service"] == "backend-gateway"


def test_ingest_valid_metric(client):
    payload = {
        "site_id": "test-frontend",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "active_users": 150,
        "request_rate": 80.0,
        "avg_response_time_ms": 65.0,
        "error_rate_percent": 0.2,
    }
    res = client.post("/api/v1/metrics", json=payload, headers={"X-API-Key": "shadow-dev-key-123"})
    assert res.status_code == 201
    data = res.json()
    assert data["status"] in ["accepted", "ingested"]
    assert data["site_id"] == "test-frontend"


def test_ingest_invalid_metric(client):
    payload = {
        "site_id": "bad-site",
        "active_users": -10,  # invalid negative
        "request_rate": 10.0,
        "avg_response_time_ms": 50.0,
        "error_rate_percent": 2.0,
    }
    res = client.post("/api/v1/metrics", json=payload, headers={"X-API-Key": "shadow-dev-key-123"})
    assert res.status_code == 422


def test_alert_manager_cooldown_and_trigger():
    import asyncio

    async def _run():
        manager = AlertManager()
        metric = MetricEvent(
            site_id="critical-site",
            timestamp=datetime.now(timezone.utc),
            active_users=5000,
            request_rate=1200.0,
            avg_response_time_ms=600.0,
            error_rate_percent=12.0,
        )
        prediction = TrafficPrediction(
            site_id="critical-site",
            predicted_at=datetime.now(timezone.utc),
            horizon_seconds=300,
            predicted_request_rate=1500.0,
            predicted_response_time_ms=750.0,
            congestion_risk_score=0.95,
            congestion_level=CongestionLevel.CRITICAL,
            recommendation="Shed load immediately",
        )

        # First alert should trigger
        alert1 = await manager.evaluate_and_notify(metric, prediction)
        assert alert1 is not None
        assert alert1.level == CongestionLevel.CRITICAL

        # Immediate second alert should be suppressed by cooldown
        alert2 = await manager.evaluate_and_notify(metric, prediction)
        assert alert2 is None

    asyncio.run(_run())
