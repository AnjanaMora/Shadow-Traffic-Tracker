import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient

from src.main import app, tenant_manager, alerting_engine


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_get_tenant_account_profile(client):
    res = client.get('/api/account')
    assert res.status_code == 200
    data = res.json()
    assert 'tenant_id' in data
    assert 'organization_name' in data
    assert 'plan_tier' in data
    assert data['registered_sites_count'] >= 3


def test_register_new_tenant_site_and_ingest(client):
    site_id = 'saas-test-store'
    reg_payload = {
        'site_id': site_id,
        'name': 'SaaS Test Electronics Store',
        'target_url': 'https://electronics.shadowtraffic.demo',
        'warning_threshold': 55.0,
        'critical_threshold': 75.0,
        'alert_webhook_url': 'https://hooks.slack.com/services/T00/B00/X00',
        'alert_email': 'ops-electronics@shadowtraffic.demo',
    }

    res_reg = client.post('/api/sites', json=reg_payload)
    assert res_reg.status_code == 201
    reg_data = res_reg.json()
    assert reg_data['site_id'] == site_id
    assert reg_data['name'] == reg_payload['name']
    generated_key = reg_data['api_key']
    assert generated_key.startswith('st_live_')
    assert 'collector_command' in reg_data
    assert generated_key in reg_data['collector_command']

    warn_thresh, crit_thresh = alerting_engine.get_site_thresholds(site_id)
    assert warn_thresh == 55.0
    assert crit_thresh == 75.0

    metric_payload = {
        'site_id': site_id,
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'active_users': 350,
        'request_rate': 180.0,
        'avg_response_time_ms': 72.5,
        'error_rate_percent': 0.1,
    }
    res_ingest = client.post(
        '/api/metrics',
        json=metric_payload,
        headers={'X-API-Key': generated_key},
    )
    assert res_ingest.status_code == 201
    assert res_ingest.json()['status'] == 'accepted'

    res_sites = client.get('/api/sites')
    assert res_sites.status_code == 200
    sites = res_sites.json()
    matched = [s for s in sites if s['site_id'] == site_id]
    assert len(matched) == 1
    assert matched[0]['name'] == reg_payload['name']
    assert matched[0]['target_url'] == reg_payload['target_url']

    # Clean up registered site
    client.delete(f'/api/sites/{site_id}')


def test_site_api_key_isolation(client):
    site_a = 'isolated-site-alpha'
    res_a = client.post(
        '/api/sites',
        json={'site_id': site_a, 'name': 'Isolated Alpha', 'target_url': 'https://alpha.demo'},
    )
    assert res_a.status_code == 201
    key_a = res_a.json()['api_key']

    site_b = 'isolated-site-beta'
    res_b = client.post(
        '/api/sites',
        json={'site_id': site_b, 'name': 'Isolated Beta', 'target_url': 'https://beta.demo'},
    )
    assert res_b.status_code == 201
    key_b = res_b.json()['api_key']

    payload_a = {
        'site_id': site_a,
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'active_users': 100,
        'request_rate': 50.0,
        'avg_response_time_ms': 30.0,
        'error_rate_percent': 0.0,
    }
    res_valid = client.post('/api/metrics', json=payload_a, headers={'X-API-Key': key_a})
    assert res_valid.status_code == 201

    payload_b_spoofed = {
        'site_id': site_b,
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'active_users': 100,
        'request_rate': 50.0,
        'avg_response_time_ms': 30.0,
        'error_rate_percent': 0.0,
    }
    res_invalid = client.post('/api/metrics', json=payload_b_spoofed, headers={'X-API-Key': key_a})
    assert res_invalid.status_code == 401
    assert 'Invalid or unauthorized API key for site' in res_invalid.json()['detail']

    # Clean up registered test sites
    client.delete(f'/api/sites/{site_a}')
    client.delete(f'/api/sites/{site_b}')


def test_site_update_and_deregister(client):
    site_id = 'lifecycle-site-demo'
    client.post(
        '/api/sites',
        json={'site_id': site_id, 'name': 'Lifecycle Demo', 'warning_threshold': 60.0, 'critical_threshold': 80.0},
    )

    update_res = client.put(
        f'/api/sites/{site_id}',
        json={'name': 'Lifecycle Demo (Renamed)', 'warning_threshold': 65.0, 'critical_threshold': 85.0},
    )
    assert update_res.status_code == 200
    updated_data = update_res.json()
    assert updated_data['name'] == 'Lifecycle Demo (Renamed)'
    assert updated_data['warning_threshold'] == 65.0

    warn, crit = alerting_engine.get_site_thresholds(site_id)
    assert warn == 65.0
    assert crit == 85.0

    del_res = client.delete(f'/api/sites/{site_id}')
    assert del_res.status_code == 200
    assert del_res.json()['status'] == 'deleted'

    del_again = client.delete(f'/api/sites/{site_id}')
    assert del_again.status_code == 404
