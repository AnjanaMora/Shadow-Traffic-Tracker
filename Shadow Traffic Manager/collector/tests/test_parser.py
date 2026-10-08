"""
Shadow Traffic — Collector Parser Unit Tests
Role in Architecture:
    Validates log parsing edge cases and Prometheus scrape parsing for the
    Collector service. Asserts that malformed or corrupted log entries are
    gracefully rejected without raising unhandled exceptions or crashing the agent.
"""

from datetime import datetime, timezone
from src.parser import AccessLogParser, PrometheusMetricsParser


def test_parse_valid_nginx_log_with_latency():
    line = (
        '192.168.1.50 - - [21/Sep/2026:14:30:15 +0000] "GET /api/v1/products HTTP/1.1" '
        '200 4520 "https://example.com" "Mozilla/5.0" 0.045'
    )
    record = AccessLogParser.parse_line(line)
    assert record is not None
    assert record.ip == "192.168.1.50"
    assert record.method == "GET"
    assert record.path == "/api/v1/products"
    assert record.status_code == 200
    assert record.bytes_sent == 4520
    assert record.response_time_ms == 45.0
    assert record.is_error is False


def test_parse_valid_apache_log_without_latency():
    line = (
        '10.0.0.1 - frank [21/Sep/2026:08:12:00 +0000] "POST /checkout HTTP/1.1" '
        '500 892 "-" "curl/7.81.0"'
    )
    record = AccessLogParser.parse_line(line)
    assert record is not None
    assert record.ip == "10.0.0.1"
    assert record.method == "POST"
    assert record.path == "/checkout"
    assert record.status_code == 500
    assert record.bytes_sent == 892
    assert record.is_error is True
    assert record.response_time_ms > 0.0  # Fallback latency


def test_parse_malformed_truncated_lines():
    # Incomplete lines must return None gracefully without raising
    assert AccessLogParser.parse_line("") is None
    assert AccessLogParser.parse_line("   \n") is None
    assert AccessLogParser.parse_line("# Comment line") is None
    assert AccessLogParser.parse_line("GET /index.html HTTP/1.1") is None
    assert AccessLogParser.parse_line("127.0.0.1 - - [21/Sep/2026") is None
    assert AccessLogParser.parse_line("RANDOM_CORRUPTED_BINARY_BYTES\x00\x01\x02") is None


def test_parse_corrupted_status_code():
    line = '192.168.1.1 - - [21/Sep/2026:10:00:00 +0000] "GET / HTTP/1.1" BAD_STATUS 123 "-" "-"'
    record = AccessLogParser.parse_line(line)
    assert record is None


def test_parse_dash_status_code():
    line = '192.168.1.1 - - [21/Sep/2026:10:00:00 +0000] "GET / HTTP/1.1" - 0 "-" "-"'
    record = AccessLogParser.parse_line(line)
    assert record is None


def test_parse_4xx_client_error():
    line = '1.2.3.4 - - [21/Sep/2026:12:00:00 +0000] "GET /not-found HTTP/1.1" 404 150 "-" "-"'
    record = AccessLogParser.parse_line(line)
    assert record is not None
    assert record.status_code == 404
    assert record.is_error is True


def test_parse_prometheus_metrics_text():
    raw_prom = """
    # HELP http_requests_total Total number of HTTP requests
    # TYPE http_requests_total counter
    http_requests_total{method="GET",status="200"} 12450
    http_requests_total{method="POST",status="500"} 120
    # HELP http_active_connections Current active TCP connections
    http_active_connections 340
    http_request_duration_seconds_sum 560.25
    http_request_duration_seconds_count 12570
    """
    parsed = PrometheusMetricsParser.parse_prometheus_text(raw_prom)
    assert "http_requests_total" in parsed
    assert len(parsed["http_requests_total"]) == 2
    assert parsed["http_active_connections"][0][1] == 340.0
    assert parsed["http_request_duration_seconds_sum"][0][1] == 560.25
