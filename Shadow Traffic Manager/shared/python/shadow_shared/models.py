from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


class CongestionLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class MetricEvent(BaseModel):
    """
    Canonical metric event representing a point-in-time telemetry snapshot of a website.
    Shared across Collector, Prediction Engine, and Backend Gateway.
    """
    model_config = ConfigDict(
        extra="ignore"
    )

    site_id: str = Field(
        ...,
        min_length=1,
        description="Unique identifier for the monitored website or service",
        examples=["store-frontend-prod"]
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp of the snapshot (UTC)"
    )
    active_users: int = Field(
        ...,
        ge=0,
        description="Number of concurrent active users / sessions during the interval",
        examples=[1450]
    )
    request_rate: float = Field(
        ...,
        ge=0.0,
        description="Incoming requests per second (RPS)",
        examples=[450.5]
    )
    avg_response_time_ms: float = Field(
        ...,
        ge=0.0,
        description="Average response time in milliseconds",
        examples=[124.8]
    )
    error_rate_percent: float = Field(
        ...,
        ge=0.0,
        le=100.0,
        description="Percentage of requests returning 4xx/5xx errors (0.0 to 100.0)",
        examples=[1.25]
    )
    is_simulated: Optional[bool] = Field(
        default=False,
        description="Flag indicating whether this telemetry event was synthetically generated"
    )
    simulated_fields: Optional[list[str]] = Field(
        default=None,
        description="List of metric fields that are simulated when polling a real target_url"
    )

    @field_validator("timestamp", mode="before")
    @classmethod
    def ensure_utc_timestamp(cls, v):
        if isinstance(v, str):
            dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        if isinstance(v, datetime) and not v.tzinfo:
            return v.replace(tzinfo=timezone.utc)
        return v


class TrafficPrediction(BaseModel):
    """
    Forecast output from the statistical and ML prediction engine.
    """
    site_id: str
    predicted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    horizon_seconds: int = Field(default=300, description="Forecast horizon in seconds (e.g., 5 minutes)")
    predicted_request_rate: float = Field(..., ge=0.0)
    predicted_response_time_ms: float = Field(..., ge=0.0)
    congestion_risk_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Congestion probability score from 0.0 (safe) to 1.0 (saturated)"
    )
    congestion_level: CongestionLevel
    recommendation: str = Field(
        default="Normal operations",
        description="Actionable mitigation advice (e.g., auto-scale, rate-limit non-critical traffic)"
    )


class AlertEvent(BaseModel):
    """
    Alert notification dispatched when congestion thresholds are breached.
    """
    alert_id: str
    site_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    level: CongestionLevel
    title: str
    message: str
    metric_snapshot: MetricEvent
    prediction: Optional[TrafficPrediction] = None


class SiteHealthStatus(BaseModel):
    site_id: str
    last_seen: datetime
    current_status: CongestionLevel
    active_users: int
    current_rps: float
    current_latency_ms: float
    current_error_rate: float
