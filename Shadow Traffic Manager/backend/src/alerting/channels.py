"""
Shadow Traffic — Pluggable Notification Channels
Role in Architecture:
    Defines the BaseNotificationChannel interface and concrete sender implementations
    for Generic Webhooks (compatible with Slack and Discord) and Email (stub/interface).
"""

import abc
import logging
from typing import Any, Dict, Optional
import httpx
from shadow_shared.models import AlertEvent, CongestionLevel

logger = logging.getLogger("backend.alerting.channels")


class BaseNotificationChannel(abc.ABC):
    """Abstract interface for all notification channel plugins."""

    @property
    @abc.abstractmethod
    def channel_name(self) -> str:
        pass

    @abc.abstractmethod
    async def send_alert(self, alert: AlertEvent) -> bool:
        """Transmit alert event to channel. Returns True on success."""
        pass


class GenericWebhookChannel(BaseNotificationChannel):
    """
    Pluggable webhook dispatcher supporting Slack, Discord, and custom JSON webhook receivers.
    """

    def __init__(self, webhook_url: Optional[str] = None):
        self.webhook_url = webhook_url

    @property
    def channel_name(self) -> str:
        return "generic-webhook"

    async def send_alert(self, alert: AlertEvent) -> bool:
        if not self.webhook_url:
            logger.debug("GenericWebhookChannel: No webhook URL configured. Skipping.")
            return False

        color_hex = {
            CongestionLevel.LOW: "#10b981",
            CongestionLevel.MEDIUM: "#f59e0b",
            CongestionLevel.HIGH: "#f97316",
            CongestionLevel.CRITICAL: "#ef4444",
        }.get(alert.level, "#6366f1")

        # Payload formatted to be simultaneously compatible with Slack, Discord, and generic webhooks
        payload: Dict[str, Any] = {
            "text": f"🚨 *[{alert.level.value}] {alert.title}*",
            "content": f"🚨 **[{alert.level.value}] {alert.title}**\n{alert.message}",
            "site_id": alert.site_id,
            "timestamp": alert.timestamp.isoformat(),
            "level": alert.level.value,
            "attachments": [
                {
                    "color": color_hex,
                    "title": alert.title,
                    "text": alert.message,
                    "fields": [
                        {"title": "Site", "value": alert.site_id, "short": True},
                        {"title": "Level", "value": alert.level.value, "short": True},
                        {"title": "Current RPS", "value": f"{alert.metric_snapshot.request_rate:.1f}", "short": True},
                        {"title": "Latency", "value": f"{alert.metric_snapshot.avg_response_time_ms:.1f} ms", "short": True},
                    ],
                }
            ],
            "embeds": [
                {
                    "title": alert.title,
                    "description": alert.message,
                    "color": int(color_hex.lstrip("#"), 16),
                    "fields": [
                        {"name": "Site", "value": alert.site_id, "inline": True},
                        {"name": "Level", "value": alert.level.value, "inline": True},
                    ],
                }
            ],
        }

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.post(self.webhook_url, json=payload)
                if res.status_code in [200, 204]:
                    logger.info(f"Webhook alert successfully dispatched to {self.webhook_url}")
                    return True
                else:
                    logger.warning(
                        f"Webhook sender rejected alert with HTTP {res.status_code}: {res.text[:120]}"
                    )
                    return False
        except Exception as exc:
            logger.error(f"Failed to transmit webhook alert: {exc}")
            return False


class EmailChannel(BaseNotificationChannel):
    """
    Extensible Email notification channel stub (for SMTP / SendGrid / AWS SES).
    """

    def __init__(self, recipient: Optional[str] = None, enabled: bool = False):
        self.recipient = recipient
        self.enabled = enabled
        self.sent_count = 0

    @property
    def channel_name(self) -> str:
        return "email-stub"

    async def send_alert(self, alert: AlertEvent) -> bool:
        if not self.enabled or not self.recipient:
            return False

        # Stub implementation: format email message and log to audit trail
        email_subject = f"[{alert.level.value} ALERT] Congestion Detected on {alert.site_id}"
        email_body = (
            f"Alert ID: {alert.alert_id}\n"
            f"Site ID: {alert.site_id}\n"
            f"Severity: {alert.level.value}\n"
            f"Time: {alert.timestamp.isoformat()}\n\n"
            f"Summary: {alert.title}\n"
            f"Details: {alert.message}\n"
        )

        logger.info(
            f"Email dispatched to {self.recipient} | Subject: '{email_subject}' | Body lines: {len(email_body.splitlines())}"
        )
        self.sent_count += 1
        return True
