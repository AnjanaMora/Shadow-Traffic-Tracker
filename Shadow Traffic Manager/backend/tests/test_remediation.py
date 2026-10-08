"""
Shadow Traffic — Auto-Remediation Unit & Integration Tests
Role in Architecture:
    Validates the automated infrastructure scaling subsystem that activates
    when traffic congestion risk reaches Critical levels.
"""

import asyncio
import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient

from shadow_shared.models import MetricEvent
from src.main import app, remediation_engine, alerting_engine


@pytest.fixture(autouse=True)
def reset_engine():
    remediation_engine.reset()
    yield
    remediation_engine.reset()


def test_remediation_triggers_scale_out_on_critical_score():
    async def _test():
        site_id = "test-remediation-ecommerce"
        metric = MetricEvent(
            site_id=site_id,
            timestamp=datetime.now(timezone.utc),
            active_users=3200,
            request_rate=850.0,
            avg_response_time_ms=650.0,
            error_rate_percent=6.2,
        )

        # Before remediation: default 2 instances
        assert remediation_engine.get_instances(site_id) == 2

        # 1. Normal traffic does NOT trigger remediation
        action_normal = await remediation_engine.evaluate_and_remediate(
            site_id=site_id,
            risk_score=25.0,
            critical_threshold=80.0,
            metric=metric,
        )
        assert action_normal is None
        assert remediation_engine.get_instances(site_id) == 2

        # 2. Critical score (>= 80.0) triggers scale-out
        action_critical = await remediation_engine.evaluate_and_remediate(
            site_id=site_id,
            risk_score=84.5,
            critical_threshold=80.0,
            metric=metric,
        )

        assert action_critical is not None
        assert action_critical.action_type == "SCALE_OUT"
        assert action_critical.previous_instances == 2
        assert action_critical.new_instances == 4
        assert action_critical.status == "COMPLETED"
        assert action_critical.message == "Auto-remediation triggered: scaled from 2 to 4 instances."
        assert remediation_engine.get_instances(site_id) == 4

        # 3. Cooldown check: second immediate Critical event returns current action without duplicate scaling
        action_cooldown = await remediation_engine.evaluate_and_remediate(
            site_id=site_id,
            risk_score=89.0,
            critical_threshold=80.0,
            metric=metric,
        )
        assert action_cooldown is not None
        assert action_cooldown.new_instances == 4
        assert remediation_engine.get_instances(site_id) == 4

    asyncio.run(_test())


def test_remediation_api_endpoints():
    client = TestClient(app)
    site_id = "test-api-remediation"

    # 1. Trigger simulated remediation via POST endpoint
    resp = client.post(f"/api/remediations/simulate/{site_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["site_id"] == site_id
    assert data["previous_instances"] == 2
    assert data["new_instances"] == 4
    assert data["message"] == "Auto-remediation triggered: scaled from 2 to 4 instances."

    # 2. Query history via GET /api/remediations
    resp_history = client.get("/api/remediations")
    assert resp_history.status_code == 200
    history = resp_history.json()
    assert len(history) >= 1
    assert history[0]["site_id"] == site_id

    # 3. Verify GET /api/status/{site_id} includes active_remediation
    resp_status = client.get(f"/api/status/{site_id}")
    assert resp_status.status_code == 200
    status_data = resp_status.json()
    assert status_data["current_instances"] == 4
    assert status_data["active_remediation"] is not None
    assert status_data["active_remediation"]["message"] == "Auto-remediation triggered: scaled from 2 to 4 instances."


def test_banner_clears_after_recovery():
    """
    Asserts that when a site's risk drops below the Warning threshold and cooldown has passed,
    the remediation engine scales in to default instances, records a SCALE_IN action, and
    clears the active remediation banner (get_active_remediation returns None).
    """
    async def _test():
        site_id = "test-recovery-site"
        # 1. Trigger Critical scale-out
        action_crit = await remediation_engine.evaluate_and_remediate(
            site_id=site_id,
            risk_score=85.0,
            warning_threshold=60.0,
            critical_threshold=80.0,
        )
        assert action_crit is not None
        assert action_crit.action_type == "SCALE_OUT"
        assert remediation_engine.get_instances(site_id) == 4
        assert remediation_engine.get_active_remediation(site_id, current_risk=85.0) is not None

        # 2. Advance time past cooldown
        from datetime import timedelta
        remediation_engine.last_action_time[site_id] = datetime.now(timezone.utc) - timedelta(seconds=remediation_engine.cooldown_seconds + 10)

        # 3. Risk drops below Warning threshold (e.g. 35.0 < 60.0)
        action_recovery = await remediation_engine.evaluate_and_remediate(
            site_id=site_id,
            risk_score=35.0,
            warning_threshold=60.0,
            critical_threshold=80.0,
        )
        assert action_recovery is None  # Active remediation returned is None
        assert remediation_engine.get_instances(site_id) == 2  # Scaled in to default

        # 4. Banner is cleared
        active = remediation_engine.get_active_remediation(site_id, current_risk=35.0)
        assert active is None

        # Check history contains both SCALE_OUT and SCALE_IN
        history = remediation_engine.get_history()
        actions = [a.action_type for a in history if a.site_id == site_id]
        assert "SCALE_IN" in actions
        assert "SCALE_OUT" in actions

    asyncio.run(_test())


def test_site_never_hit_critical_never_shows_banner():
    """
    Asserts that a site that only experiences Normal or Watch conditions (risk never hitting Critical)
    never has an active remediation banner.
    """
    async def _test():
        site_id = "test-never-critical"
        # 1. Normal risk
        act1 = await remediation_engine.evaluate_and_remediate(
            site_id=site_id,
            risk_score=20.0,
            warning_threshold=60.0,
            critical_threshold=80.0,
        )
        assert act1 is None
        assert remediation_engine.get_active_remediation(site_id, current_risk=20.0) is None

        # 2. Watch / elevated risk below warning
        act2 = await remediation_engine.evaluate_and_remediate(
            site_id=site_id,
            risk_score=50.0,
            warning_threshold=60.0,
            critical_threshold=80.0,
        )
        assert act2 is None
        assert remediation_engine.get_active_remediation(site_id, current_risk=50.0) is None
        assert remediation_engine.get_instances(site_id) == 2

    asyncio.run(_test())


def test_stale_remediation_ttl_expiration():
    """
    Asserts that if risk is no longer Critical and more than REMEDIATION_BANNER_TTL_MINUTES
    have elapsed since the remediation action, the banner is cleared.
    """
    site_id = "test-ttl-site"
    from datetime import timedelta
    from src.config import settings
    from src.remediation.models import AutoRemediationAction

    stale_time = datetime.now(timezone.utc) - timedelta(minutes=settings.REMEDIATION_BANNER_TTL_MINUTES + 1)
    remediation_engine.active_remediations[site_id] = AutoRemediationAction(
        id="rem-stale-1",
        site_id=site_id,
        timestamp=stale_time,
        trigger_score=85.0,
        action_type="SCALE_OUT",
        previous_instances=2,
        new_instances=4,
        status="COMPLETED",
        message="Stale action",
    )

    # When risk is below critical, stale action should clear and return None
    active = remediation_engine.get_active_remediation(site_id, current_risk=45.0, critical_threshold=80.0)
    assert active is None
    assert site_id not in remediation_engine.active_remediations

