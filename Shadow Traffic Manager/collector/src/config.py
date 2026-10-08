"""
Shadow Traffic — Collector Configuration
Role in Architecture:
    Defines the configuration parameters for the Shadow Traffic Collector service,
    supporting both Real Collector Mode (log tailing, Prometheus scraping) and
    Simulation Mode (diurnal traffic models, congestion injection). Reads settings
    from environment variables with production defaults.
"""

from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class CollectorSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    SERVICE_NAME: str = "shadow-collector"
    SITE_ID: str = "shadow-ecommerce-prod"
    BACKEND_API_URL: str = "http://localhost:8000"
    REPORT_INTERVAL_SECONDS: float = 3.0

    # Operational Mode: 'simulate', 'tail-log', or 'scrape-prometheus'
    COLLECTOR_MODE: str = "simulate"

    # Real Mode Settings
    LOG_FILE_PATH: Optional[str] = "/var/log/nginx/access.log"
    PROMETHEUS_METRICS_URL: Optional[str] = "http://localhost:9090/metrics"

    # Client Buffering & Retry Settings
    MAX_BUFFER_SIZE: int = 100
    RETRY_INITIAL_DELAY_SECONDS: float = 1.0
    RETRY_MAX_DELAY_SECONDS: float = 30.0
    RETRY_BACKOFF_FACTOR: float = 2.0
    REQUEST_TIMEOUT_SECONDS: float = 4.0

    # Simulation Mode Defaults
    SIM_SPEED_MULTIPLIER: float = 1.0
    SIM_BASE_USERS: int = 1200
    SIM_NOISE_PERCENT: float = 10.0
    SIM_CONGESTION_DELAY_SECONDS: float = 60.0
    SIM_CONGESTION_DURATION_SECONDS: float = 300.0
    SIM_CONGESTION_SEVERITY: float = 3.5

    LOG_LEVEL: str = "info"


settings = CollectorSettings()
