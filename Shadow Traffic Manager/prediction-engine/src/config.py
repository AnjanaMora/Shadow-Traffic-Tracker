"""
Shadow Traffic — Prediction Engine Configuration
Role in Architecture:
    Defines hyperparameters, seasonal baseline weights, critical SLA thresholds,
    and forecasting horizons for the predictive congestion engine.
"""

from typing import Dict
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    SERVICE_NAME: str = "prediction-engine"
    HOST: str = "0.0.0.0"
    PORT: int = 8001
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "info"

    # Forecasting Horizons
    FORECAST_HORIZON_MINUTES: int = 20
    CONFIDENCE_LEVEL: float = 0.90
    MIN_PROPHET_SAMPLES: int = 50

    # Baseline Parameters
    BASELINE_EWMA_ALPHA: float = 0.25  # Weekly decay factor
    MIN_STD_FLOOR: float = 0.05       # Prevents divide-by-zero on low variance

    # Metric Weighting Scheme for 0–100 Congestion Risk Score
    # Rationale:
    # - avg_response_time_ms (35%): Direct symptom of server capacity exhaustion (Little's Law).
    # - error_rate_percent (35%): Direct indicator of service degradation & SLA failure (5xx HTTP codes).
    # - request_rate (20%): Leading demand vector. High load alone is fine if latency is low.
    # - active_users (10%): Concurrency volume pressure.
    METRIC_WEIGHTS: Dict[str, float] = {
        "avg_response_time_ms": 0.35,
        "error_rate_percent": 0.35,
        "request_rate": 0.20,
        "active_users": 0.10,
    }

    # Critical SLA Thresholds for Time-to-Congestion (ETA) Estimation
    CRITICAL_THRESHOLDS: Dict[str, float] = {
        "avg_response_time_ms": 500.0,
        "error_rate_percent": 5.0,
        "request_rate": 1500.0,
        "active_users": 8000.0,
    }

    # ETA Sanity Limits
    MAX_ETA_MINUTES: float = 120.0  # Cap extrapolation at 2 hours max


settings = Settings()
