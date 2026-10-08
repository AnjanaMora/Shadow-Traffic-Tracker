"""
Shadow Traffic — Real Collector Orchestration
Role in Architecture:
    Executes live telemetry data collection from real production systems.
    Provides AccessLogTailer (tails live Nginx/Apache logs and aggregates
    requests into sliding-window MetricEvents) and PrometheusScraper (polls
    Prometheus /metrics exposition endpoints and computes interval rates).
"""

import asyncio
import logging
import os
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set
import httpx

from shadow_shared.models import MetricEvent
from .client import ResilientMetricClient
from .config import settings
from .parser import AccessLogParser, ParsedLogRecord, PrometheusMetricsParser

logger = logging.getLogger("collector.real")


class AccessLogTailer:
    """
    Tails a live web server access log file, aggregates lines over intervals,
    and pushes canonical MetricEvents via ResilientMetricClient.
    """

    def __init__(
        self,
        log_file_path: str,
        site_id: str,
        client: ResilientMetricClient,
        interval_seconds: float = settings.REPORT_INTERVAL_SECONDS,
    ):
        self.log_file_path = log_file_path
        self.site_id = site_id
        self.client = client
        self.interval_seconds = interval_seconds
        self.is_running = False

    async def run(self) -> None:
        self.is_running = True
        logger.info(f"Starting AccessLogTailer on '{self.log_file_path}' for site '{self.site_id}'")

        if not os.path.exists(self.log_file_path):
            logger.warning(
                f"Log file '{self.log_file_path}' does not exist yet. Waiting for creation..."
            )

        # Wait until file exists
        while self.is_running and not os.path.exists(self.log_file_path):
            await asyncio.sleep(2.0)

        file_obj = None
        try:
            file_obj = open(self.log_file_path, "r", encoding="utf-8", errors="replace")
            # Seek to end of file for live tailing
            file_obj.seek(0, os.SEEK_END)

            while self.is_running:
                interval_start = time.time()
                records: List[ParsedLogRecord] = []

                # Accumulate log lines for interval_seconds
                while (time.time() - interval_start) < self.interval_seconds:
                    line = file_obj.readline()
                    if line:
                        parsed = AccessLogParser.parse_line(line)
                        if parsed:
                            records.append(parsed)
                    else:
                        # No new line; yield briefly to event loop
                        await asyncio.sleep(0.1)

                # Aggregate records into MetricEvent
                event = self._aggregate_records(records)
                await self.client.push(event)

        except asyncio.CancelledError:
            logger.info("AccessLogTailer cancelled.")
        except Exception as exc:
            logger.error(f"Error tailing log file: {exc}", exc_info=True)
        finally:
            if file_obj:
                file_obj.close()

    def _aggregate_records(self, records: List[ParsedLogRecord]) -> MetricEvent:
        """Aggregate a batch of log records collected during the interval."""
        now = datetime.now(timezone.utc)
        count = len(records)
        duration = max(1.0, self.interval_seconds)

        if count == 0:
            return MetricEvent(
                site_id=self.site_id,
                timestamp=now,
                active_users=0,
                request_rate=0.0,
                avg_response_time_ms=0.0,
                error_rate_percent=0.0,
            )

        # Unique client IPs serve as approximation of concurrent active users in interval
        unique_ips: Set[str] = {r.ip for r in records}
        active_users = len(unique_ips)

        request_rate = round(count / duration, 2)
        avg_response_time = round(sum(r.response_time_ms for r in records) / count, 2)
        errors = sum(1 for r in records if r.is_error)
        error_rate_percent = round((errors / count) * 100.0, 2)

        return MetricEvent(
            site_id=self.site_id,
            timestamp=now,
            active_users=active_users,
            request_rate=request_rate,
            avg_response_time_ms=avg_response_time,
            error_rate_percent=error_rate_percent,
        )

    def stop(self) -> None:
        self.is_running = False


class PrometheusScraper:
    """
    Scrapes Prometheus /metrics exposition endpoint, calculates rate deltas,
    and posts canonical MetricEvents via ResilientMetricClient.
    """

    def __init__(
        self,
        metrics_url: str,
        site_id: str,
        client: ResilientMetricClient,
        interval_seconds: float = settings.REPORT_INTERVAL_SECONDS,
    ):
        self.metrics_url = metrics_url
        self.site_id = site_id
        self.client = client
        self.interval_seconds = interval_seconds
        self.is_running = False

        # State tracking for computing deltas
        self.last_scrape_time: Optional[float] = None
        self.last_requests_total: Optional[float] = None
        self.last_errors_total: Optional[float] = None

    async def run(self) -> None:
        self.is_running = True
        logger.info(f"Starting PrometheusScraper polling '{self.metrics_url}'")

        while self.is_running:
            try:
                event = await self._scrape_and_compute()
                if event:
                    await self.client.push(event)
            except Exception as exc:
                logger.error(f"Prometheus scrape iteration failed: {exc}")

            await asyncio.sleep(self.interval_seconds)

    async def _scrape_and_compute(self) -> Optional[MetricEvent]:
        async with httpx.AsyncClient(timeout=4.0) as http:
            resp = await http.get(self.metrics_url)
            if resp.status_code != 200:
                logger.warning(f"Prometheus scrape returned HTTP {resp.status_code}")
                return None
            body = resp.text

        metrics = PrometheusMetricsParser.parse_prometheus_text(body)
        now_ts = time.time()
        now_dt = datetime.now(timezone.utc)

        # Sum total requests and error requests across label sets
        # Standard Prometheus metrics: http_requests_total or requests_total
        requests_series = metrics.get("http_requests_total") or metrics.get("requests_total") or []
        curr_total_requests = 0.0
        curr_total_errors = 0.0

        for labels, val in requests_series:
            curr_total_requests += val
            status = labels.get("status", "") or labels.get("code", "")
            if status.startswith("4") or status.startswith("5"):
                curr_total_errors += val

        # Estimate active users from active connections or gauge
        active_conns_series = metrics.get("http_active_connections") or metrics.get("node_network_active_connections") or []
        active_users = int(active_conns_series[0][1]) if active_conns_series else 50

        # Latency approximation from duration sum / count if available
        duration_sum = metrics.get("http_request_duration_seconds_sum")
        duration_count = metrics.get("http_request_duration_seconds_count")
        avg_latency_ms = 45.0
        if duration_sum and duration_count and duration_count[0][1] > 0:
            avg_latency_ms = round((duration_sum[0][1] / duration_count[0][1]) * 1000.0, 2)

        # First iteration: initialize baseline counters
        if self.last_requests_total is None or self.last_scrape_time is None:
            self.last_requests_total = curr_total_requests
            self.last_errors_total = curr_total_errors
            self.last_scrape_time = now_ts
            return None

        # Compute rate of change
        dt = max(0.1, now_ts - self.last_scrape_time)
        delta_requests = max(0.0, curr_total_requests - self.last_requests_total)
        delta_errors = max(0.0, curr_total_errors - (self.last_errors_total or 0.0))

        rps = round(delta_requests / dt, 2)
        err_percent = round((delta_errors / delta_requests * 100.0), 2) if delta_requests > 0 else 0.0

        self.last_requests_total = curr_total_requests
        self.last_errors_total = curr_total_errors
        self.last_scrape_time = now_ts

        return MetricEvent(
            site_id=self.site_id,
            timestamp=now_dt,
            active_users=active_users,
            request_rate=rps,
            avg_response_time_ms=avg_latency_ms,
            error_rate_percent=min(100.0, err_percent),
        )

    def stop(self) -> None:
        self.is_running = False
