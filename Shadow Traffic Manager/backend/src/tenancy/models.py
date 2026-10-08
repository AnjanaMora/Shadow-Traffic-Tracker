"""
Shadow Traffic — Multi-Tenant Schemas
Role in Architecture:
    Defines data models for managing multiple independent monitored websites
    under an organization account, including per-site credentials, alert channels,
    and thresholds.
"""

from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel, Field


class SiteRegistrationRequest(BaseModel):
    """Payload for registering a new independent monitored site."""
    site_id: str = Field(..., min_length=3, max_length=64, description="Unique site identifier slug (e.g. 'checkout-api')")
    name: str = Field(..., min_length=2, max_length=128, description="Human-readable site display name")
    target_url: Optional[str] = Field(None, description="Production endpoint or domain URL being monitored")
    warning_threshold: float = Field(default=60.0, ge=10.0, le=95.0, description="Risk score threshold to trigger Warning")
    critical_threshold: float = Field(default=80.0, ge=20.0, le=100.0, description="Risk score threshold to trigger Critical")
    alert_webhook_url: Optional[str] = Field(None, description="Dedicated webhook URL for this site's alerts (Slack, Discord, PagerDuty)")
    alert_email: Optional[str] = Field(None, description="Dedicated email recipient for this site")


class SiteRegistrationResponse(BaseModel):
    """Response returned upon successful site registration, including generated API key."""
    site_id: str
    name: str
    target_url: Optional[str]
    api_key: str
    warning_threshold: float
    critical_threshold: float
    alert_webhook_url: Optional[str]
    alert_email: Optional[str]
    collector_command: str
    created_at: datetime


class SiteUpdateRequest(BaseModel):
    """Payload for updating an existing site's configuration."""
    name: Optional[str] = None
    target_url: Optional[str] = None
    warning_threshold: Optional[float] = Field(None, ge=10.0, le=95.0)
    critical_threshold: Optional[float] = Field(None, ge=20.0, le=100.0)
    alert_webhook_url: Optional[str] = None
    alert_email: Optional[str] = None


class RegisteredSiteRecord(BaseModel):
    """Internal and API record representing a tenant's registered site."""
    site_id: str
    name: str
    target_url: Optional[str] = None
    api_key: str
    warning_threshold: float = 60.0
    critical_threshold: float = 80.0
    alert_webhook_url: Optional[str] = None
    alert_email: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    is_active: bool = True


class TenantProfile(BaseModel):
    """Account and organization profile for the tenant."""
    tenant_id: str = "tenant_acme_corp"
    organization_name: str = "Acme Global Engineering"
    plan_tier: str = "Enterprise Pro"
    registered_sites_count: int = 0
    max_sites_allowed: int = 50
    master_api_key_prefix: str = "shadow-dev..."
