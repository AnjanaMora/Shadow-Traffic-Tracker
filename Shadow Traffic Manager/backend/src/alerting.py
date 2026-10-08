import logging
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Dict, List, Optional
import httpx

from shadow_shared.models import MetricEvent, TrafficPrediction, AlertEvent, CongestionLevel
from .config import settings
from .database import record_alert

logger = logging.getLogger("backend.alerting")


class AlertManager:
    def __init__(self, webhook_url: Optional[str] = settings.ALERT_WEBHOOK_URL):
        self.webhook_url = webhook_url
        self.last_alert_time: Dict[str, datetime] = {}
        self.alerts_history: deque[AlertEvent] = deque(maxlen=settings.MAX_ALERTS_HISTORY)

    async def evaluate_and_notify(
        self, metric: MetricEvent, prediction: Optional[TrafficPrediction]
    ) -> Optional[AlertEvent]:
        """
        Evaluate if an incoming metric snapshot or prediction warrants an alert.
        """
        should_alert = False
        level = CongestionLevel.LOW
        title = ""
        message = ""

        if prediction and prediction.congestion_level in [CongestionLevel.HIGH, CongestionLevel.CRITICAL]:
            should_alert = True
            level = prediction.congestion_level
            title = f"{level.value} Traffic Congestion Forecast for {metric.site_id}"
            message = (
                f"Predicted RPS: {prediction.predicted_request_rate:.1f}, "
                f"Predicted Latency: {prediction.predicted_response_time_ms:.1f}ms, "
                f"Risk Score: {prediction.congestion_risk_score:.2f}. "
                f"Recommendation: {prediction.recommendation}"
            )
        elif metric.error_rate_percent >= 5.0 or metric.avg_response_time_ms >= 500.0:
            should_alert = True
            level = CongestionLevel.CRITICAL if metric.error_rate_percent >= 10.0 else CongestionLevel.HIGH
            title = f"Live SLA Breach Detected on {metric.site_id}"
            message = (
                f"Current Latency: {metric.avg_response_time_ms:.1f}ms, "
                f"Error Rate: {metric.error_rate_percent:.2f}%, "
                f"Active Users: {metric.active_users}"
            )

        if not should_alert:
            return None

        # Check cooldown to prevent notification storms
        now = datetime.now(timezone.utc)
        last_time = self.last_alert_time.get(metric.site_id)
        if last_time and (now - last_time).total_seconds() < settings.ALERT_COOLDOWN_SECONDS:
            logger.debug(f"Alert for {metric.site_id} suppressed due to cooldown.")
            return None

        self.last_alert_time[metric.site_id] = now

        alert = AlertEvent(
            alert_id=str(uuid.uuid4())[:8],
            site_id=metric.site_id,
            timestamp=now,
            level=level,
            title=title,
            message=message,
            metric_snapshot=metric,
            prediction=prediction,
        )

        self.alerts_history.appendleft(alert)
        await record_alert(alert)
        logger.warning(f"ALERT TRIGGERED [{alert.level.value}]: {alert.title} - {alert.message}")

        # Dispatch webhook if configured
        if self.webhook_url:
            await self._dispatch_webhook(alert)

        return alert

    async def _dispatch_webhook(self, alert: AlertEvent) -> None:
        try:
            payload = {
                "text": f":warning: *{alert.title}*\n{alert.message}",
                "level": alert.level.value,
                "site_id": alert.site_id,
                "timestamp": alert.timestamp.isoformat(),
            }
            async with httpx.AsyncClient(timeout=4.0) as client:
                res = await client.post(self.webhook_url, json=payload)
                logger.info(f"Webhook alert dispatched to {self.webhook_url}: HTTP {res.status_code}")
        except Exception as exc:
            logger.error(f"Failed to dispatch webhook alert: {exc}")

    def get_recent_alerts(self, limit: int = 50) -> List[AlertEvent]:
        return list(self.alerts_history)[:limit]
