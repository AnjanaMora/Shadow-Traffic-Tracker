"""
Shadow Traffic — Hysteresis-Based Debounced Alerting Engine
Role in Architecture:
    Evaluates risk assessments and fires notifications only when a site transitions
    into an elevated status (Warning or Critical) and sustains it for >= 2 consecutive
    checks (hysteresis debouncing). Prevents flapping and alert fatigue.
"""

import logging
import uuid
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from shadow_shared.models import AlertEvent, CongestionLevel, MetricEvent, TrafficPrediction
from ..config import settings
from ..database import record_alert
from .channels import BaseNotificationChannel, GenericWebhookChannel, EmailChannel

logger = logging.getLogger("backend.alerting.engine")


class SiteHysteresisState:
    """State tracking for a single site to enforce debouncing and anti-flapping."""

    def __init__(self):
        self.confirmed_level: CongestionLevel = CongestionLevel.LOW
        self.pending_level: Optional[CongestionLevel] = None
        self.consecutive_pending_checks: int = 0
        self.last_alerted_level: Optional[CongestionLevel] = None
        self.last_alert_time: Optional[datetime] = None


class AlertingEngine:
    """
    Production alerting engine implementing hysteresis debouncing,
    pluggable notification dispatch, and database persistence.
    """

    def __init__(self, required_consecutive_checks: int = settings.HYSTERESIS_CONSECUTIVE_CHECKS):
        self.required_consecutive_checks = required_consecutive_checks
        # site_id -> SiteHysteresisState
        self.site_states: Dict[str, SiteHysteresisState] = defaultdict(SiteHysteresisState)
        # site_id -> (warning_threshold, critical_threshold)
        self.custom_thresholds: Dict[str, Tuple[float, float]] = {}

        # In-memory history for fast dashboard polling & Results slides
        self.alert_history: deque[AlertEvent] = deque(maxlen=settings.MAX_ALERTS_HISTORY)

        # Pluggable channels
        self.channels: List[BaseNotificationChannel] = [
            GenericWebhookChannel(webhook_url=settings.ALERT_WEBHOOK_URL),
            EmailChannel(
                recipient=settings.ALERT_EMAIL_RECIPIENT,
                enabled=settings.ALERT_EMAIL_ENABLED,
            ),
        ]
        # site_id -> dedicated webhook URL
        self.site_webhooks: Dict[str, str] = {}
        self.site_emails: Dict[str, str] = {}

        # Optional Root-Cause Correlator instance
        self.correlator = None

    def register_channel(self, channel: BaseNotificationChannel) -> None:
        self.channels.append(channel)

    def set_site_alert_channels(
        self,
        site_id: str,
        webhook_url: Optional[str] = None,
        email: Optional[str] = None,
    ) -> None:
        """Assigns dedicated notification destinations for a specific monitored site."""
        if webhook_url:
            self.site_webhooks[site_id] = webhook_url
        elif site_id in self.site_webhooks:
            del self.site_webhooks[site_id]

        if email:
            self.site_emails[site_id] = email
        elif site_id in self.site_emails:
            del self.site_emails[site_id]

    def set_site_thresholds(self, site_id: str, warning_score: float, critical_score: float) -> None:
        """Configures custom risk score thresholds for a specific site."""
        self.custom_thresholds[site_id] = (warning_score, critical_score)
        logger.info(
            f"Updated thresholds for '{site_id}': Warning >= {warning_score}, Critical >= {critical_score}"
        )

    def get_site_thresholds(self, site_id: str) -> Tuple[float, float]:
        return self.custom_thresholds.get(
            site_id, (settings.DEFAULT_WARNING_THRESHOLD, settings.DEFAULT_CRITICAL_THRESHOLD)
        )

    def classify_level_from_score(self, site_id: str, risk_score: float) -> CongestionLevel:
        """Determines CongestionLevel based on site-specific or default thresholds."""
        warn_thresh, crit_thresh = self.get_site_thresholds(site_id)
        if risk_score >= crit_thresh:
            return CongestionLevel.CRITICAL
        elif risk_score >= warn_thresh:
            return CongestionLevel.HIGH  # High corresponds to Warning status
        elif risk_score >= 40.0:
            return CongestionLevel.MEDIUM
        return CongestionLevel.LOW

    async def evaluate_metric_and_risk(
        self,
        metric: MetricEvent,
        risk_score: float,
        prediction: Optional[TrafficPrediction] = None,
        recommendation: Optional[str] = None,
    ) -> Optional[AlertEvent]:
        """
        Processes a new risk assessment through the hysteresis debouncer:
        1. Only fires on status transitions into Warning or Critical.
        2. Requires new status to persist for >= required_consecutive_checks.
        3. Never fires duplicate alerts while hovering in the same confirmed state.
        """
        site_id = metric.site_id
        state = self.site_states[site_id]
        observed_level = self.classify_level_from_score(site_id, risk_score)

        # 1. Check if observed level is different from confirmed level
        if observed_level != state.confirmed_level:
            if observed_level == state.pending_level:
                state.consecutive_pending_checks += 1
            else:
                state.pending_level = observed_level
                state.consecutive_pending_checks = 1

            logger.debug(
                f"Hysteresis check for '{site_id}': pending={state.pending_level.value} "
                f"({state.consecutive_pending_checks}/{self.required_consecutive_checks} checks)"
            )

            # Check if pending status has held for required consecutive checks
            if state.consecutive_pending_checks >= self.required_consecutive_checks:
                old_confirmed = state.confirmed_level
                state.confirmed_level = observed_level
                state.pending_level = None
                state.consecutive_pending_checks = 0

                logger.info(
                    f"Status transition confirmed for '{site_id}': {old_confirmed.value} -> {state.confirmed_level.value}"
                )

                # Reset last_alerted_level when dropping back to normal/medium so future spikes alert
                if state.confirmed_level in [CongestionLevel.LOW, CongestionLevel.MEDIUM]:
                    state.last_alerted_level = None

                # Only trigger alerts if transitioning INTO Warning/High or Critical
                # and this level has not already fired (or cooldown has elapsed)
                if state.confirmed_level in [CongestionLevel.HIGH, CongestionLevel.CRITICAL]:
                    is_new_level = state.confirmed_level != state.last_alerted_level
                    cooldown_expired = False
                    if not is_new_level and state.last_alert_time:
                        elapsed = (datetime.now(timezone.utc) - state.last_alert_time).total_seconds()
                        if elapsed >= settings.ALERT_COOLDOWN_SECONDS:
                            cooldown_expired = True

                    if is_new_level or cooldown_expired:
                        alert = await self._fire_alert(
                            site_id=site_id,
                            level=state.confirmed_level,
                            risk_score=risk_score,
                            metric=metric,
                            prediction=prediction,
                            recommendation=recommendation,
                        )
                        state.last_alerted_level = state.confirmed_level
                        state.last_alert_time = datetime.now(timezone.utc)
                        return alert
        else:
            # Flap reset: if observed level returned to confirmed level, reset pending candidate
            state.pending_level = None
            state.consecutive_pending_checks = 0

        return None

    async def evaluate_and_notify(
        self, metric: MetricEvent, prediction: Optional[TrafficPrediction] = None
    ) -> Optional[AlertEvent]:
        """Backward-compatible helper mapping legacy evaluate_and_notify."""
        risk_score = 85.0 if (prediction and prediction.congestion_level in [CongestionLevel.HIGH, CongestionLevel.CRITICAL]) else 20.0
        site_id = metric.site_id
        state = self.site_states[site_id]
        level = prediction.congestion_level if prediction else self.classify_level_from_score(site_id, risk_score)
        if level in [CongestionLevel.HIGH, CongestionLevel.CRITICAL] and level != state.last_alerted_level:
            alert = await self._fire_alert(
                site_id=site_id,
                level=level,
                risk_score=risk_score,
                metric=metric,
                prediction=prediction,
                recommendation=prediction.recommendation if prediction else None,
            )
            state.last_alerted_level = level
            return alert
        return None

    async def _fire_alert(
        self,
        site_id: str,
        level: CongestionLevel,
        risk_score: float,
        metric: MetricEvent,
        prediction: Optional[TrafficPrediction],
        recommendation: Optional[str],
    ) -> AlertEvent:
        """Constructs alert, saves to DB, and dispatches across all notification channels."""
        now = datetime.now(timezone.utc)
        title = f"{level.value} Congestion Alert on {site_id} (Score: {risk_score:.1f})"
        msg = (
            f"Congestion status confirmed as {level.value} (Risk Score: {risk_score:.1f}/100). "
            f"Throughput: {metric.request_rate:.1f} RPS, Latency: {metric.avg_response_time_ms:.1f} ms, "
            f"Errors: {metric.error_rate_percent:.2f}%. "
            f"Action: {recommendation or 'Inspect service capacity immediately.'}"
        )

        # Root-cause correlation check (e.g. recent software release or deployment)
        if self.correlator:
            try:
                corr = self.correlator.correlate_alert(site_id=site_id, alert_timestamp=now)
                if corr.correlated and corr.suggested_cause:
                    msg += f" Suggested Cause: {corr.suggested_cause}"
            except Exception as corr_exc:
                logger.debug(f"Root-cause correlation skipped: {corr_exc}")

        alert = AlertEvent(
            alert_id=f"alt-{uuid.uuid4().hex[:8]}",
            site_id=site_id,
            timestamp=now,
            level=level,
            title=title,
            message=msg,
            metric_snapshot=metric,
            prediction=prediction,
        )

        # Record to memory history and database audit table
        self.alert_history.appendleft(alert)
        await record_alert(alert)

        logger.warning(f"ALERT FIRED: [{alert.alert_id}] {alert.title}")

        # Dispatch asynchronously to global channels
        for channel in self.channels:
            try:
                await channel.send_alert(alert)
            except Exception as exc:
                logger.error(f"Channel {channel.channel_name} failed to dispatch alert: {exc}")

        # Dispatch to site-specific dedicated webhook if configured
        site_webhook = self.site_webhooks.get(site_id)
        if site_webhook:
            try:
                site_channel = GenericWebhookChannel(webhook_url=site_webhook)
                await site_channel.send_alert(alert)
            except Exception as exc:
                logger.error(f"Site-specific webhook for '{site_id}' failed: {exc}")

        return alert

    def remove_site(self, site_id: str) -> None:
        """Cleanly removes a site's hysteresis state, custom thresholds, channels, and cached alerts."""
        self.site_states.pop(site_id, None)
        self.custom_thresholds.pop(site_id, None)
        self.site_webhooks.pop(site_id, None)
        self.site_emails.pop(site_id, None)
        self.alert_history = deque(
            [a for a in self.alert_history if a.site_id != site_id],
            maxlen=settings.MAX_ALERTS_HISTORY,
        )
        logger.info(f"Cleaned up alerting engine state for site '{site_id}'")

    def get_alert_history(self, site_id: Optional[str] = None, limit: int = 50) -> List[AlertEvent]:
        if site_id:
            return [a for a in self.alert_history if a.site_id == site_id][:limit]
        return list(self.alert_history)[:limit]

    def clear_alerts(self, site_id: Optional[str] = None, alert_id: Optional[str] = None) -> int:
        """
        Clears alert history globally, for a specific site, or for a specific alert_id.
        Returns the count of alerts cleared.
        """
        initial_count = len(self.alert_history)
        if alert_id:
            self.alert_history = deque(
                [a for a in self.alert_history if a.alert_id != alert_id],
                maxlen=settings.MAX_ALERTS_HISTORY,
            )
        elif site_id:
            self.alert_history = deque(
                [a for a in self.alert_history if a.site_id != site_id],
                maxlen=settings.MAX_ALERTS_HISTORY,
            )
        else:
            self.alert_history.clear()
        
        cleared = initial_count - len(self.alert_history)
        logger.info(f"Cleared {cleared} alert(s) (site_id={site_id}, alert_id={alert_id})")
        return cleared
