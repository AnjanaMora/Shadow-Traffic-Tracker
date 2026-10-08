"""
Shadow Traffic — Storage Models & DTOs
Role in Architecture:
    Defines typed models for query results returned by TimescaleDB continuous
    aggregates (1-minute and 5-minute rollups) and raw hypertable queries.
"""

from datetime import datetime
from pydantic import BaseModel, Field
from shadow_shared.models import MetricEvent, CongestionLevel, TrafficPrediction, AlertEvent


class MetricRollup(BaseModel):
    """
    Continuous aggregate rollup summary representing a pre-computed time bucket.
    """
    bucket: datetime
    site_id: str
    sample_count: int = Field(..., ge=0)

    avg_active_users: int = Field(..., ge=0)
    max_active_users: int = Field(..., ge=0)

    avg_request_rate: float = Field(..., ge=0.0)
    max_request_rate: float = Field(..., ge=0.0)
    p95_request_rate: float = Field(..., ge=0.0)

    avg_response_time_ms: float = Field(..., ge=0.0)
    max_response_time_ms: float = Field(..., ge=0.0)
    p95_response_time_ms: float = Field(..., ge=0.0)

    avg_error_rate_percent: float = Field(..., ge=0.0, le=100.0)
    max_error_rate_percent: float = Field(..., ge=0.0, le=100.0)


__all__ = [
    "MetricEvent",
    "MetricRollup",
    "CongestionLevel",
    "TrafficPrediction",
    "AlertEvent",
]
