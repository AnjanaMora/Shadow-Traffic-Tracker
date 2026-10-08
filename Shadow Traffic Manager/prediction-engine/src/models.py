"""
Shadow Traffic — Prediction Engine Data Models
Role in Architecture:
    Defines typed data models for the prediction engine:
    ForecastInterval, ContributingFactor, and RiskAssessment output payloads.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, Field
from shadow_shared.models import MetricEvent, TrafficPrediction, CongestionLevel


class RiskStatus(str, Enum):
    NORMAL = "Normal"        # 0–39: Within healthy seasonal limits
    WATCH = "Watch"          # 40–59: Minor divergence or upward velocity
    WARNING = "Warning"      # 60–79: Significant congestion risk before SLA breach
    CRITICAL = "Critical"    # 80–100: Immediate saturation or SLA failure


class ForecastInterval(BaseModel):
    """
    Forward-looking metric forecast with confidence bounds.
    """
    metric_name: str
    horizon_minutes: int
    yhat: float
    yhat_lower: float
    yhat_upper: float
    confidence_level: float = 0.90
    model_used: str = "prophet"  # 'prophet' or 'statsmodels'


class ContributingFactor(BaseModel):
    """
    Explainable metric attribution detailing its role in the overall risk score.
    """
    metric: str
    current_value: float
    baseline_mean: float
    baseline_std: float
    z_score: float
    forecast_value: float
    percentage_contribution: float
    reason: str


class RiskAssessment(BaseModel):
    """
    Comprehensive output payload combining seasonal baseline comparison,
    ML forecasting, 0–100 risk scoring, explainable factors, and congestion ETA.
    """
    site_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    score: float = Field(..., ge=0.0, le=100.0, description="Congestion Risk Score (0–100)")
    status: RiskStatus
    eta_minutes: Optional[float] = Field(
        default=None,
        description="Estimated minutes until critical threshold breach, capped at 120 minutes"
    )
    primary_bottleneck: Optional[str] = None
    contributing_factors: List[ContributingFactor] = Field(default_factory=list)
    forecasts: Dict[str, ForecastInterval] = Field(default_factory=dict)
    recommendation: str


__all__ = [
    "MetricEvent",
    "TrafficPrediction",
    "CongestionLevel",
    "RiskStatus",
    "ForecastInterval",
    "ContributingFactor",
    "RiskAssessment",
]
