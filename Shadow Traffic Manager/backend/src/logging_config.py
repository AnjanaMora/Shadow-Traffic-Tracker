"""
Shadow Traffic — Structured JSON Logging
Role in Architecture:
    Formats application log records as structured JSON for centralized log
    aggregation (Datadog, Loki, CloudWatch) in production container environments.
"""

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any, Dict


class JSONLogFormatter(logging.Formatter):
    """
    Serializes Python logging records into structured JSON lines.
    """

    def format(self, record: logging.LogRecord) -> str:
        log_entry: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service": "shadow-backend",
        }

        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        # Include custom extra attributes if provided
        if hasattr(record, "site_id"):
            log_entry["site_id"] = getattr(record, "site_id")

        return json.dumps(log_entry)


def setup_logging(json_format: bool = True, log_level: str = "INFO") -> None:
    """Configure root logger with structured JSON or standard console format."""
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level.upper())

    # Clear existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    if json_format:
        handler.setFormatter(JSONLogFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        )

    root_logger.addHandler(handler)
