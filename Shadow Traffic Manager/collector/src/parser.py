"""
Shadow Traffic — Telemetry Log & Prometheus Metric Parser
Role in Architecture:
    Extracts raw telemetry data from web server access logs (Nginx, Apache) or
    Prometheus /metrics scrape endpoints. Handles all malformed input gracefully
    without raising unhandled exceptions, ensuring uninterrupted metric collection.
"""

import re
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("collector.parser")

# Regex for Nginx/Apache Combined Log Format with optional response time at end:
# $remote_addr - $remote_user [$time_local] "$request" $status $body_bytes_sent "$http_referer" "$http_user_agent" [$request_time]
LOG_PATTERN = re.compile(
    r'^(?P<ip>\S+)\s+'
    r'(?P<ident>\S+)\s+'
    r'(?P<user>\S+)\s+'
    r'\[(?P<time>[^\]]+)\]\s+'
    r'"(?P<request>[^"]*)"\s+'
    r'(?P<status>\d{3}|-)\s+'
    r'(?P<bytes>\d+|-)'
    r'(?:\s+"(?P<referer>[^"]*)")?'
    r'(?:\s+"(?P<agent>[^"]*)")?'
    r'(?:\s+(?P<response_time>[\d\.]+))?'
)

PROMETHEUS_LINE_PATTERN = re.compile(
    r'^(?P<metric_name>[a-zA-Z_:][a-zA-Z0-9_:]*)'
    r'(?:\{(?P<labels>[^}]+)\})?'
    r'\s+(?P<value>[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?|NaN|[+-]?Inf)'
    r'(?:\s+(?P<timestamp>\d+))?$'
)


@dataclass
class ParsedLogRecord:
    ip: str
    timestamp: datetime
    method: str
    path: str
    status_code: int
    bytes_sent: int
    response_time_ms: float
    is_error: bool


class AccessLogParser:
    """
    Parses web server access log lines with robust error suppression.
    """

    @staticmethod
    def parse_line(line: str) -> Optional[ParsedLogRecord]:
        """
        Parse a single access log line.
        Returns ParsedLogRecord on success, or None if the line is invalid/malformed.
        Guarantees never to crash or raise exceptions on bad input.
        """
        cleaned = line.strip()
        if not cleaned or cleaned.startswith("#"):
            return None

        match = LOG_PATTERN.match(cleaned)
        if not match:
            logger.debug(f"Skipping malformed or unrecognized log line: {cleaned[:80]}...")
            return None

        data = match.groupdict()

        # Parse status code
        status_str = data.get("status")
        if not status_str or status_str == "-":
            return None
        try:
            status_code = int(status_str)
        except ValueError:
            return None

        # Parse timestamp: format e.g. "21/Sep/2026:10:00:00 +0000"
        time_str = data.get("time")
        dt = datetime.now(timezone.utc)
        if time_str:
            try:
                # Standard Common Log format
                dt = datetime.strptime(time_str.split()[0], "%d/%b/%Y:%H:%M:%S").replace(
                    tzinfo=timezone.utc
                )
            except Exception:
                dt = datetime.now(timezone.utc)

        # Parse request string: e.g. "GET /api/v1/checkout HTTP/1.1"
        req_str = data.get("request", "")
        parts = req_str.split()
        method = parts[0].upper() if parts else "UNKNOWN"
        path = parts[1] if len(parts) > 1 else "/"

        # Parse bytes
        try:
            bytes_sent = int(data.get("bytes") or 0)
        except ValueError:
            bytes_sent = 0

        # Parse response time (in seconds -> convert to ms, or already in ms)
        resp_time_ms = 25.0  # sensible fallback if not logged
        resp_time_raw = data.get("response_time")
        if resp_time_raw:
            try:
                val = float(resp_time_raw)
                # If val < 10.0, assume it was logged in seconds (e.g. 0.045s -> 45ms)
                resp_time_ms = val * 1000.0 if val < 100.0 else val
            except ValueError:
                pass

        # Error if HTTP status >= 400
        is_error = 400 <= status_code <= 599

        return ParsedLogRecord(
            ip=data.get("ip", "127.0.0.1"),
            timestamp=dt,
            method=method,
            path=path,
            status_code=status_code,
            bytes_sent=bytes_sent,
            response_time_ms=resp_time_ms,
            is_error=is_error,
        )


class PrometheusMetricsParser:
    """
    Parses Prometheus text exposition format into rate and latency summaries.
    """

    @staticmethod
    def parse_prometheus_text(text: str) -> Dict[str, List[Tuple[Dict[str, str], float]]]:
        """
        Parses Prometheus scrape text into a structured mapping:
        { metric_name: [({label_key: label_val}, value), ...] }
        """
        metrics: Dict[str, List[Tuple[Dict[str, str], float]]] = {}

        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            match = PROMETHEUS_LINE_PATTERN.match(line)
            if not match:
                continue

            name = match.group("metric_name")
            labels_str = match.group("labels")
            value_str = match.group("value")

            try:
                value = float(value_str)
            except ValueError:
                continue

            labels: Dict[str, str] = {}
            if labels_str:
                for part in re.finditer(r'([a-zA-Z_0-9]+)="([^"]*)"', labels_str):
                    labels[part.group(1)] = part.group(2)

            if name not in metrics:
                metrics[name] = []
            metrics[name].append((labels, value))

        return metrics
