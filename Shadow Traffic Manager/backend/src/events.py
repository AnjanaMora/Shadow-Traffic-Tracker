"""
Shadow Traffic — Deployment & Incident Event Schemas
Role in Architecture:
    Records deployment, configuration, and infrastructure lifecycle events
    to enable automated root-cause correlation when alerts trigger.
"""

from datetime import datetime, timezone
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field


class DeploymentEvent(BaseModel):
    """Event representing a software deployment or release rollout."""
    event_id: str = Field(..., description="Unique event ID (e.g. 'dep-20260921-1402')")
    site_id: str = Field(..., description="Target site/service identifier")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Timestamp of deployment")
    service: str = Field(..., description="Service or component name deployed (e.g. 'checkout-api')")
    version: str = Field(..., description="Git commit hash or release tag (e.g. 'v2.4.1')")
    deployed_by: Optional[str] = Field("ci/cd-pipeline", description="Engineer or automation pipeline that deployed")
    description: Optional[str] = Field(None, description="Change summary or release notes")
    environment: str = Field("production", description="Target environment")


class CorrelationResult(BaseModel):
    """Root-cause correlation result explaining potential drivers of an alert."""
    correlated: bool = False
    event_type: Optional[str] = None
    time_delta_minutes: Optional[float] = None
    suggested_cause: Optional[str] = None
    details: Optional[Dict[str, Any]] = None