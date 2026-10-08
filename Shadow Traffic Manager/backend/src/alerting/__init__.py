"""
Shadow Traffic — Alerting Package
Role in Architecture:
    Alerting engine with hysteresis debouncing and pluggable notification channels.
"""

from .engine import AlertingEngine
from .channels import BaseNotificationChannel, GenericWebhookChannel, EmailChannel

AlertManager = AlertingEngine

__all__ = [
    "AlertingEngine",
    "AlertManager",
    "BaseNotificationChannel",
    "GenericWebhookChannel",
    "EmailChannel",
]
