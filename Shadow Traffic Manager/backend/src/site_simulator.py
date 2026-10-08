"""
Shadow Traffic — Per-Site Background Simulation Manager
Role in Architecture:
    Manages dedicated background asyncio tasks for registered websites so that
    every site added via POST /api/sites immediately produces realistic, live
    synthetic telemetry without requiring an external collector process.

    Feeds metrics directly through the core ingestion and alerting pipeline:
    storage DAL -> prediction engine -> hysteresis alerting engine -> WebSockets.
"""

import asyncio
import logging
import math
import random
import time
from datetime import datetime, timezone, timedelta
from typing import Callable, Coroutine, Dict, Optional

from shadow_shared.models import MetricEvent

logger = logging.getLogger("backend.site_simulator")


class SiteTrafficSimulator:
    """
    Simulates organic website traffic and configurable congestion events for a specific site.
    """

    def __init__(
        self,
        site_id: str,
        target_url: Optional[str] = None,
        base_users: int = 1200,
        noise_percent: float = 8.0,
        speed_multiplier: float = 1.0,
        congestion_delay_seconds: float = 60.0,
        congestion_duration_seconds: float = 180.0,
        congestion_severity: float = 3.5,
        start_time: Optional[datetime] = None,
    ):
        self.site_id = site_id
        self.target_url = target_url
        self.base_users = base_users
        self.noise_percent = noise_percent
        self.speed_multiplier = max(0.1, speed_multiplier)
        self.congestion_delay_seconds = congestion_delay_seconds
        self.congestion_duration_seconds = congestion_duration_seconds
        self.congestion_severity = congestion_severity

        self.sim_time = start_time or datetime.now(timezone.utc)
        self.elapsed_sim_seconds: float = 0.0
        self.is_congested: bool = False

        # Real URL polling state
        self.real_latency: Optional[float] = None
        self.real_error_rate: Optional[float] = None
        self.last_poll_time: float = 0.0
        self.poll_interval_seconds: float = 60.0

    async def poll_target_url(self) -> None:
        """
        Politely polls the real target_url at a 60s minimum interval for real response time
        and availability status.
        """
        if not self.target_url or not self.target_url.startswith("http"):
            return
        now = time.time()
        if (now - self.last_poll_time) < self.poll_interval_seconds:
            return
        self.last_poll_time = now
        try:
            import httpx
            t_start = time.time()
            async with httpx.AsyncClient(timeout=5.0, follow_redirects=True) as client:
                resp = await client.get(self.target_url)
                self.real_latency = round((time.time() - t_start) * 1000.0, 2)
                self.real_error_rate = 0.0 if resp.status_code < 400 else 100.0
        except Exception as exc:
            logger.debug(f"Polite external poll for '{self.site_id}' ({self.target_url}) error: {exc}")
            self.real_latency = 500.0
            self.real_error_rate = 100.0

    @staticmethod
    def calculate_diurnal_factor(dt: datetime) -> float:
        hour = dt.hour + (dt.minute / 60.0) + (dt.second / 3600.0)
        angle = ((hour - 14.0) / 24.0) * 2.0 * math.pi
        raw_curve = (math.cos(angle) + 1.0) / 2.0
        return 0.35 + (raw_curve * 1.30)

    @staticmethod
    def calculate_weekend_factor(dt: datetime) -> float:
        if dt.weekday() >= 5:
            return 0.80
        return 1.0

    def trigger_congestion_event(self, duration_seconds: Optional[float] = None) -> None:
        """Forces an immediate congestion ramp."""
        self.congestion_delay_seconds = self.elapsed_sim_seconds
        if duration_seconds:
            self.congestion_duration_seconds = duration_seconds
        self.is_congested = True
        logger.info(f"Triggered immediate congestion event on site '{self.site_id}'")

    def generate_next_metric(self, step_seconds: float = 3.0) -> MetricEvent:
        delta = step_seconds * self.speed_multiplier
        self.elapsed_sim_seconds += delta
        self.sim_time += timedelta(seconds=delta)
        # Keep timestamp fresh to current real time so dashboards and queries are live
        now_utc = datetime.now(timezone.utc)

        diurnal = self.calculate_diurnal_factor(now_utc)
        weekend = self.calculate_weekend_factor(now_utc)
        seasonal_multiplier = diurnal * weekend

        congestion_multiplier = 1.0
        congestion_progress = 0.0

        if self.elapsed_sim_seconds >= self.congestion_delay_seconds:
            time_into = self.elapsed_sim_seconds - self.congestion_delay_seconds
            if time_into < self.congestion_duration_seconds:
                self.is_congested = True
                congestion_progress = time_into / self.congestion_duration_seconds
                ramp = (1.0 - math.cos(congestion_progress * math.pi)) / 2.0
                congestion_multiplier = 1.0 + (ramp * (self.congestion_severity - 1.0))
            elif time_into < (self.congestion_duration_seconds * 1.5):
                recovery = (time_into - self.congestion_duration_seconds) / (self.congestion_duration_seconds * 0.5)
                ramp = max(0.0, 1.0 - recovery)
                congestion_multiplier = 1.0 + (ramp * (self.congestion_severity - 1.0))
                congestion_progress = ramp
                self.is_congested = False
            else:
                self.is_congested = False

        noise_std = (self.noise_percent / 100.0) * self.base_users
        noise = random.gauss(0, noise_std)
        raw_users = (self.base_users * seasonal_multiplier * congestion_multiplier) + noise
        active_users = max(20, int(raw_users))

        user_rps_ratio = 0.35 + random.uniform(-0.03, 0.03)
        request_rate = max(1.0, round(active_users * user_rps_ratio, 2))

        base_latency = 38.0 + random.uniform(-3, 5)
        base_error = max(0.01, random.uniform(0.05, 0.20))

        if congestion_progress > 0.0:
            latency_degradation = (congestion_progress ** 1.6) * 450.0
            avg_response_time = base_latency + latency_degradation

            if congestion_progress > 0.50:
                error_spike_progress = (congestion_progress - 0.50) / 0.50
                error_surge = (error_spike_progress ** 2.2) * 24.0
                error_rate = min(95.0, base_error + error_surge)
            else:
                error_rate = base_error + (congestion_progress * 0.5)
        else:
            avg_response_time = base_latency
            error_rate = base_error

        # If we have polled a real target_url and are not under congestion testing, use real metrics
        simulated_fields = None
        if self.target_url and self.target_url.startswith("http"):
            if self.real_latency is not None and not self.is_congested:
                avg_response_time = self.real_latency
            if self.real_error_rate is not None and not self.is_congested:
                error_rate = self.real_error_rate
            simulated_fields = ["active_users", "request_rate"]
        else:
            simulated_fields = ["active_users", "request_rate", "avg_response_time_ms", "error_rate_percent"]

        return MetricEvent(
            site_id=self.site_id,
            timestamp=now_utc,
            active_users=active_users,
            request_rate=round(request_rate, 2),
            avg_response_time_ms=round(avg_response_time, 2),
            error_rate_percent=round(error_rate, 2),
            is_simulated=True,
            simulated_fields=simulated_fields,
        )


class SimulationRegistry:
    """Manages active simulation tasks and their simulators per site."""

    def __init__(self):
        self.tasks: Dict[str, asyncio.Task] = {}
        self.simulators: Dict[str, SiteTrafficSimulator] = {}
        self.last_external_ingest: Dict[str, float] = {}

    def note_external_ingest(self, site_id: str) -> None:
        self.last_external_ingest[site_id] = time.time()

    def is_external_active(self, site_id: str, timeout_seconds: float = 6.0) -> bool:
        last = self.last_external_ingest.get(site_id, 0)
        return (time.time() - last) < timeout_seconds

    def start_simulation(
        self,
        site_id: str,
        ingest_fn: Callable[[MetricEvent], Coroutine],
        target_url: Optional[str] = None,
        interval_seconds: float = 3.0,
        base_users: int = 1200,
        congestion_delay_seconds: float = 60.0,
        congestion_duration_seconds: float = 180.0,
        congestion_severity: float = 3.5,
    ) -> None:
        """Spawns an in-process background simulation task without creating duplicates."""
        # If task is already running, avoid spawning duplicate
        if site_id in self.tasks and not self.tasks[site_id].done():
            logger.debug(f"Simulation task for site '{site_id}' already running.")
            return

        self.stop_simulation(site_id)

        sim = SiteTrafficSimulator(
            site_id=site_id,
            target_url=target_url,
            base_users=base_users,
            congestion_delay_seconds=congestion_delay_seconds,
            congestion_duration_seconds=congestion_duration_seconds,
            congestion_severity=congestion_severity,
        )
        self.simulators[site_id] = sim

        async def _run():
            logger.info(f"Started in-process simulation loop for site '{site_id}'")
            try:
                while True:
                    # For sites with real target_url, poll at polite interval (>=60s)
                    if sim.target_url:
                        try:
                            await sim.poll_target_url()
                        except Exception as poll_ex:
                            logger.debug(f"Target url poll error for '{site_id}': {poll_ex}")

                    # If external collector is currently pushing metrics, gracefully yield
                    if not self.is_external_active(site_id):
                        try:
                            metric = sim.generate_next_metric(step_seconds=interval_seconds)
                            await ingest_fn(metric)
                        except Exception as ex:
                            logger.debug(f"Simulation tick error for '{site_id}': {ex}")

                    await asyncio.sleep(interval_seconds)
            except asyncio.CancelledError:
                logger.info(f"Simulation task for site '{site_id}' cancelled.")

        task = asyncio.create_task(_run())
        self.tasks[site_id] = task

    def stop_simulation(self, site_id: str) -> bool:
        """Cancels and clears the simulation task for site_id."""
        task = self.tasks.pop(site_id, None)
        self.simulators.pop(site_id, None)
        if task and not task.done():
            task.cancel()
            logger.info(f"Stopped simulation task for site '{site_id}'")
            return True
        return False

    def stop_all(self) -> None:
        """Stops all running simulation tasks."""
        for site_id in list(self.tasks.keys()):
            self.stop_simulation(site_id)

    def trigger_congestion(self, site_id: str, duration_seconds: Optional[float] = None) -> bool:
        sim = self.simulators.get(site_id)
        if sim:
            sim.trigger_congestion_event(duration_seconds=duration_seconds)
            return True
        return False

    def get_simulator(self, site_id: str) -> Optional[SiteTrafficSimulator]:
        return self.simulators.get(site_id)

    def list_simulated_sites(self) -> list:
        return [sid for sid, t in self.tasks.items() if not t.done()]


simulation_registry = SimulationRegistry()
