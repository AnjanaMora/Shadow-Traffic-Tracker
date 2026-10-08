"""
Shadow Traffic — Root-Cause Correlation Unit & Integration Tests
Role in Architecture:
    Verifies that when deployments are recorded, any subsequent alert
    occurring within the correlation window surfaces the deployment as
    the suggested cause ("Risk spike correlates with deployment at HH:MM").
"""

from datetime import datetime, timezone, timedelta
import pytest
from fastapi.testclient import TestClient

from shadow_shared.models import MetricEvent, CongestionLevel
from src.main import app, root_cause_correlator, alerting_engine
from src.events import DeploymentEvent


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_deployment_recording_and_listing(client):
    """Verifies that deployments can be posted and retrieved."""
    dep_payload = {
        "event_id": "dep-checkout-test-01",
        "site_id": "checkout-corr-site",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service": "checkout-api",
        "version": "v2.4.1",
        "deployed_by": "alice@ops.demo",
        "description": "Upgraded payment provider SDK and connection pool size",
        "environment": "production",
    }
    res = client.post("/api/deployments", json=dep_payload)
    assert res.status_code == 201
    data = res.json()
    assert data["event_id"] == "dep-checkout-test-01"
    assert data["version"] == "v2.4.1"

    # List deployments
    res_list = client.get("/api/deployments?site_id=checkout-corr-site")
    assert res_list.status_code == 200
    deps = res_list.json()
    assert len(deps) >= 1
    assert deps[0]["site_id"] == "checkout-corr-site"


def test_root_cause_correlation_surfaces_in_alert():
    """
    Verifies that when an alert is fired shortly after a recorded deployment,
    the alert message includes the suggested cause linking the deployment.
    """
    import asyncio

    async def _run():
        site_id = "corr-test-service"
        deploy_time = datetime.now(timezone.utc) - timedelta(minutes=4.0)

        # 1. Record deployment 4 minutes ago
        root_cause_correlator.record_deployment(
            DeploymentEvent(
                event_id="dep-2026-v3",
                site_id=site_id,
                timestamp=deploy_time,
                service="auth-service",
                version="v3.1.0-rc2",
            )
        )

        # 2. Trigger high congestion metric
        now = datetime.now(timezone.utc)
        metric = MetricEvent(
            site_id=site_id,
            timestamp=now,
            active_users=3000,
            request_rate=950.0,
            avg_response_time_ms=520.0,
            error_rate_percent=6.5,
        )

        # Simulate consecutive checks to satisfy hysteresis debouncing
        alerting_engine.site_states[site_id].consecutive_pending_checks = 1
        alerting_engine.site_states[site_id].pending_level = CongestionLevel.CRITICAL

        alert = await alerting_engine.evaluate_metric_and_risk(
            metric=metric,
            risk_score=88.0,
        )

        assert alert is not None
        assert "Suggested Cause:" in alert.message
        assert "v3.1.0-rc2" in alert.message
        time_str = deploy_time.strftime("%H:%M")
        assert f"at {time_str}" in alert.message

    asyncio.run(_run())