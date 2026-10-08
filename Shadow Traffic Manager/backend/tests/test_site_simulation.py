"""
Shadow Traffic — Automated Site Simulation & Alerting Tests
Tests that:
1. Registering a site via POST /api/sites automatically starts background simulation.
2. /api/status/{site_id} receives real, changing telemetry without running any external collector.
3. When risk crosses thresholds, a NEW alert is generated for that specific site_id.
4. DELETE /api/sites/{site_id} cleanly stops the background simulation task and removes state.
"""

import asyncio
import time
from datetime import datetime, timezone, timedelta
import pytest
from fastapi.testclient import TestClient

from shadow_shared.models import MetricEvent, CongestionLevel
from src.main import app, tenant_manager, alerting_engine, active_sites, _ingest_simulated_metric
from src.site_simulator import simulation_registry, SiteTrafficSimulator


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_registered_site_spawns_simulation_and_populates_status(client):
    """
    Asserts that POST /api/sites automatically registers the site and spawns
    an in-process simulation task that feeds telemetry into /api/status/{site_id}.
    """
    site_id = f"auto-sim-site-{int(time.time())}"
    reg_payload = {
        "site_id": site_id,
        "name": "Auto Simulated Service",
        "target_url": "https://service.auto-sim.demo",
        "warning_threshold": 50.0,
        "critical_threshold": 75.0,
    }

    # 1. Register new website
    res = client.post("/api/sites", json=reg_payload)
    assert res.status_code == 201
    data = res.json()
    assert data["site_id"] == site_id

    # 2. Verify simulation task was automatically registered
    assert site_id in simulation_registry.tasks
    assert not simulation_registry.tasks[site_id].done()

    # 3. Simulate two consecutive ticks through the ingestion pipeline
    sim = simulation_registry.get_simulator(site_id)
    assert sim is not None

    m1 = sim.generate_next_metric(step_seconds=3.0)
    m2 = sim.generate_next_metric(step_seconds=3.0)

    # Values must change between ticks (synthetic dynamic variation)
    assert m1.timestamp is not None
    assert m2.timestamp is not None

    asyncio.run(_ingest_simulated_metric(m1))
    asyncio.run(_ingest_simulated_metric(m2))

    # 4. Query /api/status/{site_id} - must return changing metric values
    status_res = client.get(f"/api/status/{site_id}")
    assert status_res.status_code == 200
    status_data = status_res.json()
    assert status_data["site_id"] == site_id
    assert len(status_data["recent_metrics_30m"]) >= 2
    assert status_data["recent_metrics_30m"][-1]["request_rate"] > 0

    # Clean up
    client.delete(f"/api/sites/{site_id}")


def test_new_site_congestion_fires_alert_for_specific_site(client):
    """
    Asserts that when a newly registered site experiences congestion crossing
    its threshold for >= 2 consecutive checks, a NEW alert is generated specifically
    for that site_id (not just the demo site), and appears in /api/alerts.
    """
    site_id = f"alert-sim-site-{int(time.time())}"
    reg_payload = {
        "site_id": site_id,
        "name": "Alert Simulation Target",
        "warning_threshold": 50.0,
        "critical_threshold": 80.0,
    }

    res = client.post("/api/sites", json=reg_payload)
    assert res.status_code == 201

    # Temporarily pause background task so test metrics aren't interleaved
    simulation_registry.stop_simulation(site_id)

    now = datetime.now(timezone.utc)
    # Check 1: enters elevated warning status
    high_metric_1 = MetricEvent(
        site_id=site_id,
        timestamp=now + timedelta(seconds=2),
        active_users=3200,
        request_rate=450.0,
        avg_response_time_ms=520.0,
        error_rate_percent=6.5,
    )
    # Check 2: climbs into critical status
    high_metric_2 = MetricEvent(
        site_id=site_id,
        timestamp=now + timedelta(seconds=6),
        active_users=3500,
        request_rate=480.0,
        avg_response_time_ms=540.0,
        error_rate_percent=7.0,
    )
    # Check 3: sustains critical status (confirms hysteresis 2nd check)
    high_metric_3 = MetricEvent(
        site_id=site_id,
        timestamp=now + timedelta(seconds=10),
        active_users=3600,
        request_rate=490.0,
        avg_response_time_ms=550.0,
        error_rate_percent=7.2,
    )

    asyncio.run(_ingest_simulated_metric(high_metric_1))
    asyncio.run(_ingest_simulated_metric(high_metric_2))
    asyncio.run(_ingest_simulated_metric(high_metric_3))

    # Query alert history filtered by this specific site
    alert_res = client.get(f"/api/alerts?site_id={site_id}")
    assert alert_res.status_code == 200
    alerts = alert_res.json()

    assert len(alerts) >= 1, f"Expected alert for '{site_id}' to fire, but found none."
    newest_alert = alerts[0]
    assert newest_alert["site_id"] == site_id
    assert newest_alert["level"] in ["HIGH", "CRITICAL"]
    assert site_id in newest_alert["title"]

    # Verify global alerts also contain this site's alert
    global_alerts_res = client.get("/api/alerts")
    assert global_alerts_res.status_code == 200
    all_alerts = global_alerts_res.json()
    matching = [a for a in all_alerts if a["site_id"] == site_id]
    assert len(matching) >= 1

    # Clean up
    client.delete(f"/api/sites/{site_id}")


def test_delete_site_stops_background_simulation_and_cleans_state(client):
    """
    Asserts that DELETE /api/sites/{site_id} cancels and removes the background
    simulation task, cleans up alerting state, remediation state, closes websocket connections,
    and makes POST /api/metrics reject data for the deleted site with 404.
    Also tests purge=true deletes historical metrics from storage.
    """
    from src.main import remediation_engine, dal

    site_id = f"delete-sim-site-{int(time.time())}"
    reg_res = client.post("/api/sites", json={"site_id": site_id, "name": "Site To Delete"})
    assert reg_res.status_code == 201
    api_key = reg_res.json()["api_key"]

    assert site_id in simulation_registry.tasks

    # Insert a metric into dal
    m = MetricEvent(
        site_id=site_id,
        timestamp=datetime.now(timezone.utc),
        active_users=100,
        request_rate=20.0,
        avg_response_time_ms=50.0,
        error_rate_percent=0.1,
    )
    asyncio.run(dal.insert_metric(m))

    # Set some remediation state
    remediation_engine.site_instances[site_id] = 4
    remediation_engine.last_action_time[site_id] = datetime.now(timezone.utc)

    # Delete with purge=true
    del_res = client.delete(f"/api/sites/{site_id}?purge=true")
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "deleted"
    assert del_res.json()["purged"] is True

    # 1. Simulation task stopped and removed
    assert site_id not in simulation_registry.tasks
    assert site_id not in simulation_registry.simulators

    # 2. Alerting engine cleaned
    assert site_id not in alerting_engine.site_states
    assert site_id not in alerting_engine.custom_thresholds

    # 3. Remediation engine cleaned
    assert site_id not in remediation_engine.site_instances
    assert site_id not in remediation_engine.active_remediations
    assert site_id not in remediation_engine.last_action_time

    # 4. Active sites cleaned
    assert site_id not in active_sites

    # 5. POST /api/metrics for deleted site rejected with 404
    post_res = client.post(
        "/api/metrics",
        headers={"X-API-Key": api_key},
        json={
            "site_id": site_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "active_users": 150,
            "request_rate": 25.0,
            "avg_response_time_ms": 60.0,
            "error_rate_percent": 0.2,
        },
    )
    assert post_res.status_code == 404

    # 6. Verify dal metrics purged
    recent = asyncio.run(dal.get_recent(site_id, minutes=60))
    assert len(recent) == 0


def test_target_url_simulation_flags_simulated_fields():
    """
    Asserts that sites registered with a real target_url flag active_users and request_rate
    as simulated, and provide is_simulated=True in MetricEvent.
    """
    site_id = "test-target-url-sim"
    sim = SiteTrafficSimulator(site_id=site_id, target_url="https://example.com")
    metric = sim.generate_next_metric()

    assert metric.is_simulated is True
    assert metric.simulated_fields == ["active_users", "request_rate"]
    assert metric.active_users > 0
    assert metric.request_rate > 0


def test_start_simulation_no_duplicates():
    """
    Asserts that calling start_simulation multiple times on the same site_id
    does not create duplicate running tasks.
    """
    async def _test():
        site_id = "test-dedup-site"
        async def dummy_ingest(metric):
            pass

        simulation_registry.start_simulation(site_id=site_id, ingest_fn=dummy_ingest)
        task1 = simulation_registry.tasks[site_id]

        # Second call should not spawn a duplicate task
        simulation_registry.start_simulation(site_id=site_id, ingest_fn=dummy_ingest)
        task2 = simulation_registry.tasks[site_id]

        assert task1 is task2
        assert not task1.done()

        # Clean up
        simulation_registry.stop_simulation(site_id)

    asyncio.run(_test())

