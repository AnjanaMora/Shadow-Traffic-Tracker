"""
Shadow Traffic — Unified Structured JSON Logging
================================================
Standardized JSON logging formatter and setup utility shared across all
Shadow Traffic Python microservices (Backend Gateway, Prediction Engine, Collector).
Enables zero-friction ingestion into Datadog, Loki, CloudWatch, or Docker JSON logs.
"""

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Optional


class StructuredJSONFormatter(logging.Formatter):
    """
    Serializes Python logging records into structured JSON lines conforming to
    production log aggregation standards.
    """

    def __init__(self, service_name: str = "shadow-traffic"):
        super().__init__()
        self.service_name = service_name

    def format(self, record: logging.LogRecord) -> str:
        log_entry: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "service": self.service_name,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Include contextual fields if attached to the record
        for attr in ("site_id", "status", "risk_score", "eta_minutes", "metric_name", "client_ip", "path"):
            if hasattr(record, attr):
                log_entry[attr] = getattr(record, attr)

        # Include exception tracebacks if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry, default=str)


def setup_structured_logging(
    service_name: str,
    log_level: str = "INFO",
    json_format: bool = True
) -> None:
    """
    Configures the root logger with either JSON structured formatting or human-readable console text.
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level.upper())

    # Remove pre-existing handlers to prevent log duplication
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    stream_handler = logging.StreamHandler(sys.stdout)
    if json_format:
        stream_handler.setFormatter(StructuredJSONFormatter(service_name=service_name))
    else:
        stream_handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] (%(name)s): %(message)s")
        )

    root_logger.addHandler(stream_handler)
