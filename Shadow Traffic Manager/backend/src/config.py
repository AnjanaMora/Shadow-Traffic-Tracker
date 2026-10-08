"""
Shadow Traffic — Backend Gateway Configuration
Role in Architecture:
    Central configuration for the core API Gateway, security mechanisms,
    rate limiting, hysteresis-based alerting, and notification channels.
"""

from typing import Dict, Optional, Set
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    SERVICE_NAME: str = "backend-gateway"
    HOST: str = "0.0.0.0"
    PORT: int = 8080
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "info"
    LOG_FORMAT_JSON: bool = True
    CORS_ALLOWED_ORIGINS: str = "*"

    # Database Settings
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/shadow_traffic"
    DATABASE_POOL_SIZE: int = 20

    # Prediction Engine service URL
    PREDICTION_ENGINE_URL: str = "http://localhost:8001"

    # Security & API Key Authentication
    ENABLE_API_KEY_AUTH: bool = True
    DEFAULT_API_KEY: str = "shadow-dev-key-123"
    ALLOWED_API_KEYS: Set[str] = {"shadow-dev-key-123", "prod-collector-key-999"}

    # Rate Limiting (per site_id)
    RATE_LIMIT_REQUESTS_PER_MINUTE: int = 60  # Allows 1 req/sec average with burst headroom

    # Alerting & Hysteresis
    HYSTERESIS_CONSECUTIVE_CHECKS: int = 2     # Must persist for N checks before firing
    ALERT_COOLDOWN_SECONDS: int = 60           # Minimum cooldown between repeat alerts
    DEFAULT_WARNING_THRESHOLD: float = 60.0
    DEFAULT_CRITICAL_THRESHOLD: float = 80.0

    # Notification Channels
    ALERT_WEBHOOK_URL: Optional[str] = None
    ALERT_EMAIL_ENABLED: bool = False
    ALERT_EMAIL_RECIPIENT: Optional[str] = "alerts@shadowtraffic.internal"

    MAX_ALERTS_HISTORY: int = 100

    # Auto-Remediation & Cloud Scaling Settings
    AUTOSCALE_WEBHOOK_URL: Optional[str] = None
    AUTOSCALE_COOLDOWN_SECONDS: int = 180
    DEFAULT_INITIAL_INSTANCES: int = 2
    DEFAULT_SCALE_STEP: int = 2
    REMEDIATION_BANNER_TTL_MINUTES: int = 5


settings = Settings()
