"""
Shadow Traffic — Prediction Engine FastAPI Microservice
Role in Architecture:
    Exposes HTTP endpoints for early-warning congestion forecasting:
    - POST /predict/{site_id}: Computes full RiskAssessment (0-100 score, status, ETA, explainability)
    - POST /predict: Backward-compatible endpoint for legacy clients
    - GET /health: Healthcheck endpoint for Docker Compose
"""

import logging
from typing import List, Optional
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from shadow_shared.models import MetricEvent, TrafficPrediction, CongestionLevel
from shadow_shared.logging import setup_structured_logging
from .config import settings
from .models import RiskAssessment, RiskStatus
from .service import assess_risk

setup_structured_logging(
    service_name=settings.SERVICE_NAME,
    log_level=settings.LOG_LEVEL,
    json_format=True,
)
logger = logging.getLogger(settings.SERVICE_NAME)

app = FastAPI(
    title="Shadow Traffic — Prediction Engine",
    description="Seasonal Baseline Modeling, Dual Forecasting & Explainable Congestion Risk Service",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AssessmentRequest(BaseModel):
    current_window: List[MetricEvent]
    historical_data: Optional[List[MetricEvent]] = None


class LegacyPredictionRequest(BaseModel):
    current_metric: MetricEvent
    history: Optional[List[MetricEvent]] = None


@app.get("/health", tags=["Health"])
async def health_check():
    return {
        "status": "healthy",
        "service": settings.SERVICE_NAME,
        "environment": settings.ENVIRONMENT,
        "horizons_minutes": settings.FORECAST_HORIZON_MINUTES,
    }


@app.post("/predict/{site_id}", response_model=RiskAssessment, tags=["Forecasting"])
async def predict_site_risk(site_id: str, req: AssessmentRequest):
    """
    Run full prediction pipeline:
    - Seasonal baseline lookup by (day_of_week, hour_of_day)
    - Forward forecasting with confidence intervals
    - 0–100 Congestion Risk Score with metric attribution
    - Time-to-congestion (ETA) extrapolation
    """
    if not req.current_window:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="current_window cannot be empty",
        )

    try:
        assessment = assess_risk(
            site_id=site_id,
            current_window=req.current_window,
            historical_data=req.historical_data,
        )
        return assessment
    except Exception as exc:
        logger.error(f"Error computing risk assessment for {site_id}: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Prediction pipeline error: {str(exc)}",
        )


@app.post("/predict", response_model=TrafficPrediction, tags=["Forecasting"])
async def legacy_predict(req: LegacyPredictionRequest):
    """
    Backward-compatible endpoint for existing pipeline stages.
    Translates RiskAssessment into canonical TrafficPrediction model.
    """
    window = req.history or [req.current_metric]
    if req.current_metric not in window:
        window.append(req.current_metric)

    try:
        assessment = assess_risk(
            site_id=req.current_metric.site_id,
            current_window=window,
        )

        # Map RiskStatus to CongestionLevel
        level_map = {
            RiskStatus.NORMAL: CongestionLevel.LOW,
            RiskStatus.WATCH: CongestionLevel.MEDIUM,
            RiskStatus.WARNING: CongestionLevel.HIGH,
            RiskStatus.CRITICAL: CongestionLevel.CRITICAL,
        }
        mapped_level = level_map.get(assessment.status, CongestionLevel.LOW)

        rps_fc = assessment.forecasts.get("request_rate")
        lat_fc = assessment.forecasts.get("avg_response_time_ms")

        return TrafficPrediction(
            site_id=assessment.site_id,
            predicted_at=assessment.timestamp,
            horizon_seconds=settings.FORECAST_HORIZON_MINUTES * 60,
            predicted_request_rate=rps_fc.yhat if rps_fc else req.current_metric.request_rate,
            predicted_response_time_ms=lat_fc.yhat if lat_fc else req.current_metric.avg_response_time_ms,
            congestion_risk_score=round(assessment.score / 100.0, 4),
            congestion_level=mapped_level,
            recommendation=assessment.recommendation,
        )
    except Exception as exc:
        logger.error(f"Legacy predict error: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Prediction engine error: {str(exc)}",
        )
