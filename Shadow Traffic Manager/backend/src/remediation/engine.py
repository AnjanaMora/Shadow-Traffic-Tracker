"""
Shadow Traffic — Auto-Remediation Execution Engine
Role in Architecture:
    Executes automated infrastructure actions (e.g., auto-scaling server
    instances) when traffic congestion risk breaches Critical thresholds,
    moving the system from predictive early-warning to proactive closed-loop action.
"""

import asyncio
import logging
import time
import uuid
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import httpx

from shadow_shared.models import MetricEvent
from ..config import settings
from .models import AutoRemediationAction

logger = logging.getLogger("backend.remediation.engine")


class AutoRemediationEngine:
    """
    Automated infrastructure remediation engine that monitors risk assessments
    and triggers cloud auto-scale actions when risk reaches Critical.
    """

    def __init__(
        self,
        webhook_url: Optional[str] = settings.AUTOSCALE_WEBHOOK_URL,
        cooldown_seconds: int = settings.AUTOSCALE_COOLDOWN_SECONDS,
        default_instances: int = settings.DEFAULT_INITIAL_INSTANCES,
        scale_step: int = settings.DEFAULT_SCALE_STEP,
        max_instances: int = 8,
    ):
        self.webhook_url = webhook_url
        self.cooldown_seconds = cooldown_seconds
        self.default_instances = default_instances
        self.scale_step = scale_step
        self.max_instances = max_instances

        # site_id -> current instance count (default 2)
        self.site_instances: Dict[str, int] = defaultdict(lambda: self.default_instances)

        # site_id -> timestamp of last remediation action
        self.last_action_time: Dict[str, datetime] = {}

        # site_id -> latest active remediation action
        self.active_remediations: Dict[str, AutoRemediationAction] = {}

        # Global audit log of remediation actions
        self.remediation_history: deque[AutoRemediationAction] = deque(maxlen=100)

    def get_instances(self, site_id: str) -> int:
        """Returns the current instance count for the specified site."""
        return self.site_instances[site_id]

    def get_active_remediation(
        self,
        site_id: str,
        current_risk: Optional[float] = None,
        critical_threshold: float = 80.0,
    ) -> Optional[AutoRemediationAction]:
        """
        Returns the active remediation action if genuinely relevant:
        - Current risk is at or above Critical threshold, OR
        - Action occurred within the last REMEDIATION_BANNER_TTL_MINUTES.
        Otherwise clears and returns None.
        """
        action = self.active_remediations.get(site_id)
        if not action:
            return None

        now = datetime.now(timezone.utc)
        action_time = action.timestamp
        if action_time.tzinfo is None:
            action_time = action_time.replace(tzinfo=timezone.utc)
        elapsed_minutes = (now - action_time).total_seconds() / 60.0

        is_at_critical = (current_risk is not None and current_risk >= critical_threshold)
        is_within_ttl = (elapsed_minutes <= settings.REMEDIATION_BANNER_TTL_MINUTES)

        if is_at_critical or is_within_ttl:
            return action

        # Action is stale / no longer relevant
        self.active_remediations.pop(site_id, None)
        return None

    def remove_site(self, site_id: str) -> None:
        """Cleanly removes all remediation state for a site."""
        self.site_instances.pop(site_id, None)
        self.active_remediations.pop(site_id, None)
        self.last_action_time.pop(site_id, None)
        logger.info(f"Cleaned up remediation engine state for site '{site_id}'")

    def get_history(self, limit: int = 50) -> List[AutoRemediationAction]:
        """Returns the chronological history of executed remediation actions."""
        return list(self.remediation_history)[:limit]

    def reset(self) -> None:
        """Resets engine state (used during test suites)."""
        self.site_instances.clear()
        self.last_action_time.clear()
        self.active_remediations.clear()
        self.remediation_history.clear()

    async def _dispatch_webhook(
        self,
        site_id: str,
        action_type: str,
        previous_instances: int,
        new_instances: int,
        trigger_score: float,
    ) -> Tuple[int, float]:
        """
        Dispatches async HTTP call to cloud auto-scaler webhook or executes
        an internal mock simulation of an AWS / Kubernetes scale event.
        """
        payload = {
            "event": "autoscale_trigger",
            "site_id": site_id,
            "action": action_type,
            "previous_instances": previous_instances,
            "desired_instances": new_instances,
            "trigger_risk_score": trigger_score,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        t_start = time.time()

        if self.webhook_url and self.webhook_url.startswith("http"):
            try:
                async with httpx.AsyncClient(timeout=4.0) as client:
                    resp = await client.post(self.webhook_url, json=payload)
                    latency = round((time.time() - t_start) * 1000.0, 2)
                    return resp.status_code, latency
            except Exception as exc:
                logger.warning(
                    f"External autoscale webhook '{self.webhook_url}' failed: {exc}. Falling back to mock execution."
                )

        # Mock / Simulated cloud provider response (AWS EC2 / Kubernetes HPA)
        await asyncio.sleep(0.05)  # brief non-blocking simulated network trip
        latency = round((time.time() - t_start) * 1000.0 + 95.0, 2)
        return 200, latency

    async def evaluate_and_remediate(
        self,
        site_id: str,
        risk_score: float,
        warning_threshold: float = 60.0,
        critical_threshold: float = 80.0,
        metric: Optional[MetricEvent] = None,
    ) -> Optional[AutoRemediationAction]:
        """
        Evaluates risk score. If risk score crosses Critical and cooldown has
        elapsed, automatically scales out the instance capacity.
        When risk drops below Warning threshold and cooldown has elapsed,
        scales back in and clears active remediation.
        """
        now = datetime.now(timezone.utc)
        current_instances = self.site_instances[site_id]

        # ---------------------------------------------------------------------
        # SCALE OUT: Triggered on Critical Congestion Risk
        # ---------------------------------------------------------------------
        if risk_score >= critical_threshold:
            # Check cooldown
            last_time = self.last_action_time.get(site_id)
            if last_time and (now - last_time).total_seconds() < self.cooldown_seconds:
                # Still in cooldown from previous remediation
                return self.get_active_remediation(site_id, current_risk=risk_score, critical_threshold=critical_threshold)

            # Check capacity ceiling
            if current_instances >= self.max_instances:
                logger.warning(
                    f"Site '{site_id}' is at maximum capacity ({current_instances} instances); cannot scale further."
                )
                return self.get_active_remediation(site_id, current_risk=risk_score, critical_threshold=critical_threshold)

            new_instances = min(self.max_instances, current_instances + self.scale_step)

            # Dispatch mock cloud auto-scale webhook
            status_code, latency_ms = await self._dispatch_webhook(
                site_id=site_id,
                action_type="SCALE_OUT",
                previous_instances=current_instances,
                new_instances=new_instances,
                trigger_score=risk_score,
            )

            message = f"Auto-remediation triggered: scaled from {current_instances} to {new_instances} instances."

            action = AutoRemediationAction(
                id=f"rem-{uuid.uuid4().hex[:8]}",
                site_id=site_id,
                timestamp=now,
                trigger_score=risk_score,
                action_type="SCALE_OUT",
                previous_instances=current_instances,
                new_instances=new_instances,
                provider="AWS Auto Scaling / Kubernetes HPA (Simulated)",
                status="COMPLETED" if status_code < 400 else "FAILED",
                message=message,
                webhook_status_code=status_code,
                execution_latency_ms=latency_ms,
            )

            # Structured operational log
            logger.warning(
                f"Auto-remediation triggered for site '{site_id}': scaled from {current_instances} to {new_instances} instances.",
                extra={
                    "site_id": site_id,
                    "action": "SCALE_OUT",
                    "previous_instances": current_instances,
                    "new_instances": new_instances,
                    "trigger_score": risk_score,
                },
            )

            # Commit state
            self.site_instances[site_id] = new_instances
            self.last_action_time[site_id] = now
            self.active_remediations[site_id] = action
            self.remediation_history.appendleft(action)

            return action

        # ---------------------------------------------------------------------
        # SCALE IN & BANNER CLEAR: Triggered when risk drops below Warning threshold
        # ---------------------------------------------------------------------
        elif risk_score < warning_threshold:
            last_time = self.last_action_time.get(site_id)
            cooldown_passed = (last_time is None) or ((now - last_time).total_seconds() >= self.cooldown_seconds)
            if cooldown_passed:
                if current_instances > self.default_instances:
                    new_instances = self.default_instances
                    status_code, latency_ms = await self._dispatch_webhook(
                        site_id=site_id,
                        action_type="SCALE_IN",
                        previous_instances=current_instances,
                        new_instances=new_instances,
                        trigger_score=risk_score,
                    )

                    message = f"Auto-remediation recovery: scaled in from {current_instances} to {new_instances} instances."
                    action = AutoRemediationAction(
                        id=f"rem-{uuid.uuid4().hex[:8]}",
                        site_id=site_id,
                        timestamp=now,
                        trigger_score=risk_score,
                        action_type="SCALE_IN",
                        previous_instances=current_instances,
                        new_instances=new_instances,
                        provider="AWS Auto Scaling / Kubernetes HPA (Simulated)",
                        status="COMPLETED",
                        message=message,
                        webhook_status_code=status_code,
                        execution_latency_ms=latency_ms,
                    )

                    logger.info(
                        f"Auto-remediation recovery for site '{site_id}': scaled in from {current_instances} to {new_instances} instances."
                    )

                    self.site_instances[site_id] = new_instances
                    self.last_action_time[site_id] = now
                    self.remediation_history.appendleft(action)

                # Clear active remediation so banner clears
                self.active_remediations.pop(site_id, None)
                return None

        # Return active remediation only if genuinely relevant (within TTL or still at Critical)
        return self.get_active_remediation(site_id, current_risk=risk_score, critical_threshold=critical_threshold)
