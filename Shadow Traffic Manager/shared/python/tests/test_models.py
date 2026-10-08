import json
import pytest
from datetime import datetime, timezone
from pydantic import ValidationError
from shadow_shared.models import MetricEvent, CongestionLevel, TrafficPrediction, AlertEvent


def test_valid_metric_event():
    event = MetricEvent(
        site_id="ecommerce-checkout",
        timestamp=datetime.now(timezone.utc),
        active_users=1200,
        request_rate=350.5,
        avg_response_time_ms=85.2,
        error_rate_percent=0.8
    )
    assert event.site_id == "ecommerce-checkout"
    assert event.active_users == 1200
    assert event.request_rate == 350.5
    assert event.avg_response_time_ms == 85.2
    assert event.error_rate_percent == 0.8


def test_metric_event_json_serialization():
    event = MetricEvent(
        site_id="api-gateway",
        timestamp=datetime(2026, 9, 21, 10, 0, 0, tzinfo=timezone.utc),
        active_users=500,
        request_rate=120.0,
        avg_response_time_ms=45.0,
        error_rate_percent=0.1
    )
    payload = json.loads(event.model_dump_json())
    assert payload["site_id"] == "api-gateway"
    assert payload["active_users"] == 500
    assert payload["timestamp"].startswith("2026-09-21T10:00:00")


def test_invalid_negative_metric_values():
    with pytest.raises(ValidationError):
        MetricEvent(
            site_id="site-a",
            active_users=-5,
            request_rate=10.0,
            avg_response_time_ms=10.0,
            error_rate_percent=1.0
        )


def test_invalid_error_rate_over_100():
    with pytest.raises(ValidationError):
        MetricEvent(
            site_id="site-a",
            active_users=10,
            request_rate=10.0,
            avg_response_time_ms=10.0,
            error_rate_percent=105.0
        )


def test_extra_fields_forbidden():
    with pytest.raises(ValidationError):
        MetricEvent(
            site_id="site-a",
            active_users=10,
            request_rate=10.0,
            avg_response_time_ms=10.0,
            error_rate_percent=1.0,
            unknown_field="injected"
        )


def test_canonical_json_schema_matches_pydantic():
    from pathlib import Path
    import jsonschema

    schema_file = Path(__file__).parents[2] / "schema" / "metric_event.json"
    assert schema_file.exists()

    with open(schema_file, "r", encoding="utf-8") as f:
        schema = json.load(f)

    event = MetricEvent(
        site_id="test-canonical-site",
        timestamp=datetime.now(timezone.utc),
        active_users=2500,
        request_rate=780.2,
        avg_response_time_ms=115.4,
        error_rate_percent=0.75,
    )
    event_dict = json.loads(event.model_dump_json())

    # Validate that Pydantic's serialized payload strictly conforms to the JSON Schema
    jsonschema.validate(instance=event_dict, schema=schema)

