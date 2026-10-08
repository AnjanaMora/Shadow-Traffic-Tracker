"""
Shadow Traffic — Risk Assessment Service Orchestrator
Role in Architecture:
    Exposes the core assess_risk() pipeline function. Coordinates seasonal
    baseline extraction, forward forecasting with confidence intervals,
    explainable risk scoring, and time-to-congestion ETA estimation.
"""

import logging
from typing import Dict, List, Optional
from datetime import datetime, timezone

from shadow_shared.models import MetricEvent
from .baseline import SeasonalBaselineModel
from .forecaster import DualForecaster
from .models import ForecastInterval, RiskAssessment
from .risk_scorer import RiskScorer

logger = logging.getLogger("prediction.service")

baseline_model = SeasonalBaselineModel()
forecaster = DualForecaster()
risk_scorer = RiskScorer()


def assess_risk(
    site_id: str,
    current_window: List[MetricEvent],
    historical_data: Optional[List[MetricEvent]] = None,
) -> RiskAssessment:
    """
    Core pipeline function:
    1. Fits/updates seasonal baseline with historical data (if provided).
    2. Retrieves expected mean and std for the current time slot.
    3. Generates 15–30m forward forecast with confidence intervals.
    4. Calculates 0–100 Congestion Risk Score, status, contributing factors, and ETA.
    """
    if not current_window:
        raise ValueError("current_window must contain at least one MetricEvent")

    # 1. Update baseline if historical batch provided
    if historical_data:
        baseline_model.fit_events(site_id, historical_data)

    # Sort window chronologically
    sorted_window = sorted(current_window, key=lambda e: e.timestamp)
    latest_metric = sorted_window[-1]

    # Also update baseline with current observation
    baseline_model.update_single(latest_metric)

    # 2. Extract baseline expected (mean, std) for each metric
    metric_names = ["avg_response_time_ms", "error_rate_percent", "request_rate", "active_users"]
    baselines: Dict[str, tuple[float, float]] = {}
    for m in metric_names:
        baselines[m] = baseline_model.get_baseline(site_id, m, latest_metric.timestamp)

    # 3. Forecast each metric 15–30 minutes forward
    forecasts: Dict[str, ForecastInterval] = {}
    for m in metric_names:
        # Build series of (timestamp, value)
        series = [(e.timestamp, float(getattr(e, m))) for e in sorted_window]
        forecasts[m] = forecaster.forecast(metric_name=m, series=series)

    # 4. Compute composite risk, explainable factors, and ETA
    (
        score,
        status,
        eta_minutes,
        primary_bottleneck,
        contributing_factors,
        recommendation,
    ) = risk_scorer.calculate_risk(
        current_metric=latest_metric,
        baselines=baselines,
        forecasts=forecasts,
        recent_window=sorted_window,
    )

    assessment = RiskAssessment(
        site_id=site_id,
        timestamp=latest_metric.timestamp,
        score=score,
        status=status,
        eta_minutes=eta_minutes,
        primary_bottleneck=primary_bottleneck,
        contributing_factors=contributing_factors,
        forecasts=forecasts,
        recommendation=recommendation,
    )

    logger.info(
        f"Assessed risk for '{site_id}': Score={score} ({status.value}), "
        f"ETA={eta_minutes}m, Top Bottleneck='{primary_bottleneck}'"
    )
    return assessment
