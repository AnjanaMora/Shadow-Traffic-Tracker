"""
Shadow Traffic — Automated Root-Cause Correlation Engine
Role in Architecture:
    Maintains a rolling ledger of system events (deployments, config updates)
    and automatically inspects chronological correlation when alerts trigger.
    Surfaces human-readable hypotheses (e.g. Risk spike correlates with deployment v2.4.1 at 14:02 (3.5 mins prior)).
"""

import logging
from collections import deque
from datetime import datetime, timezone
from typing import List, Optional
from .events import DeploymentEvent, CorrelationResult

logger = logging.getLogger("backend.correlation")


class RootCauseCorrelator:
    """
    Correlates incident alerts with recent operational events.
    """

    def __init__(self, max_history: int = 500, correlation_window_minutes: float = 30.0):
        self.max_history = max_history
        self.correlation_window_minutes = correlation_window_minutes
        self.deployments: deque[DeploymentEvent] = deque(maxlen=max_history)

    def record_deployment(self, event: DeploymentEvent) -> DeploymentEvent:
        """Records a new deployment event into the chronological ledger."""
        self.deployments.appendleft(event)
        logger.info(
            f"Recorded deployment '{event.event_id}' for site '{event.site_id}' "
            f"version={event.version} at {event.timestamp.isoformat()}"
        )
        return event

    def get_deployments(self, site_id: Optional[str] = None, limit: int = 50) -> List[DeploymentEvent]:
        """Lists recent deployment events, optionally filtered by site_id."""
        if site_id:
            return [d for d in self.deployments if d.site_id == site_id][:limit]
        return list(self.deployments)[:limit]

    def correlate_alert(self, site_id: str, alert_timestamp: datetime) -> CorrelationResult:
        """
        Inspects if any deployment for site_id occurred within the lookback window
        immediately preceding the alert timestamp.
        """
        best_candidate: Optional[DeploymentEvent] = None
        min_delta_minutes: Optional[float] = None

        for dep in self.deployments:
            if dep.site_id != site_id:
                continue

            delta = (alert_timestamp - dep.timestamp).total_seconds() / 60.0

            if -2.0 <= delta <= self.correlation_window_minutes:
                if min_delta_minutes is None or abs(delta) < abs(min_delta_minutes):
                    min_delta_minutes = delta
                    best_candidate = dep

        if best_candidate and min_delta_minutes is not None:
            time_str = best_candidate.timestamp.strftime("%H:%M")
            delta_rounded = round(min_delta_minutes, 1)

            if delta_rounded < 0:
                cause_msg = (
                    f"Risk spike correlates with deployment '{best_candidate.version}' "
                    f"underway at {time_str} ({abs(delta_rounded)} min window)."
                )
            else:
                cause_msg = (
                    f"Risk spike correlates with deployment '{best_candidate.version}' "
                    f"at {time_str} ({delta_rounded} mins prior)."
                )

            logger.warning(f"Root-cause correlation for site '{site_id}': {cause_msg}")
            return CorrelationResult(
                correlated=True,
                event_type="DEPLOYMENT",
                time_delta_minutes=delta_rounded,
                suggested_cause=cause_msg,
                details=best_candidate.model_dump(mode="json"),
            )

        return CorrelationResult(correlated=False)