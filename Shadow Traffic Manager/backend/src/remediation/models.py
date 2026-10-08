"""
Shadow Traffic — Auto-Remediation Models
Role in Architecture:
    Defines schemas for automated infrastructure scaling actions triggered
    when traffic congestion risk breaches Critical thresholds.
"""

from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel, Field


class AutoRemediationAction(BaseModel):
    """Represents a completed or in-progress auto-remediation scaling event."""
    id: str = Field(..., description="Unique remediation action identifier")
    site_id: str = Field(..., description="Monitored site identifier")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp when action was executed",
    )
    trigger_score: float = Field(..., description="Risk score that triggered this remediation")
    action_type: str = Field(default="SCALE_OUT", description="Type of action (SCALE_OUT, SCALE_IN)")
    previous_instances: int = Field(default=2, description="Cluster instance count before scaling")
    new_instances: int = Field(default=4, description="Cluster instance count after scaling")
    provider: str = Field(
        default="AWS Auto Scaling (Simulated)",
        description="Target cloud or orchestrator provider (AWS, GCP, Kubernetes HPA)",
    )
    status: str = Field(default="COMPLETED", description="Execution status (COMPLETED, FAILED)")
    message: str = Field(
        default="Auto-remediation triggered: scaled from 2 to 4 instances.",
        description="Human-readable remediation summary",
    )
    webhook_status_code: Optional[int] = Field(
        default=200,
        description="HTTP response status code from auto-scale webhook",
    )
    execution_latency_ms: Optional[float] = Field(
        default=120.0,
        description="Simulated or measured cloud API execution latency in milliseconds",
    )
