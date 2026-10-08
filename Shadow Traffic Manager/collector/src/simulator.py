"""
Shadow Traffic — Traffic Simulation Engine
Role in Architecture:
    Generates synthetic, highly realistic web telemetry with circadian diurnal
    oscillations, weekday/weekend traffic patterns, Gaussian jitter, and staged
    congestion event injection. Allows testing and benchmarking the prediction
    engine without requiring live production traffic.
"""

import math
import random
from datetime import datetime, timezone, timedelta
from typing import Optional
from shadow_shared.models import MetricEvent
from .config import settings


class TrafficSimulator:
    """
    Simulates organic website traffic and configurable congestion events.
    """

    def __init__(
        self,
        site_id: str = settings.SITE_ID,
        base_users: int = settings.SIM_BASE_USERS,
        noise_percent: float = settings.SIM_NOISE_PERCENT,
        speed_multiplier: float = settings.SIM_SPEED_MULTIPLIER,
        congestion_delay_seconds: float = settings.SIM_CONGESTION_DELAY_SECONDS,
        congestion_duration_seconds: float = settings.SIM_CONGESTION_DURATION_SECONDS,
        congestion_severity: float = settings.SIM_CONGESTION_SEVERITY,
        start_time: Optional[datetime] = None,
    ):
        self.site_id = site_id
        self.base_users = base_users
        self.noise_percent = noise_percent
        self.speed_multiplier = max(0.1, speed_multiplier)
        self.congestion_delay_seconds = congestion_delay_seconds
        self.congestion_duration_seconds = congestion_duration_seconds
        self.congestion_severity = congestion_severity

        # Virtual clock
        self.sim_time = start_time or datetime.now(timezone.utc)
        self.elapsed_sim_seconds: float = 0.0

        # Congestion injection state
        self.congestion_injected = False
        self.is_congested = False

    def generate_metric(self) -> MetricEvent:
        """Convenience alias for generate_next_metric."""
        return self.generate_next_metric()

    @staticmethod
    def calculate_diurnal_factor(dt: datetime) -> float:
        """
        Calculates time-of-day seasonal factor:
        - 9:00 AM - 9:00 PM: Peak traffic (1.2x - 1.7x)
        - 1:00 AM - 6:00 AM: Overnight lull (0.3x - 0.5x)
        - Smooth transition in between
        """
        hour = dt.hour + (dt.minute / 60.0) + (dt.second / 3600.0)

        # Diurnal curve modeled via a smooth cosine/sine mix centered around 14:00 (2pm)
        # Shift so peak is at 14:00 (hour 14), trough at 03:00 (hour 3)
        angle = ((hour - 14.0) / 24.0) * 2.0 * math.pi
        raw_curve = (math.cos(angle) + 1.0) / 2.0  # Range: [0.0, 1.0]

        # Map to [0.35, 1.65] range
        diurnal_factor = 0.35 + (raw_curve * 1.30)
        return diurnal_factor

    @staticmethod
    def calculate_weekend_factor(dt: datetime) -> float:
        """
        Slight day-of-week variation:
        - Monday - Friday: 1.0x (full business traffic)
        - Saturday - Sunday: ~0.80x (weekend traffic drop)
        """
        # weekday(): Monday is 0 and Sunday is 6
        if dt.weekday() >= 5:
            return 0.80
        return 1.0

    def trigger_congestion_event(self, duration_seconds: Optional[float] = None) -> None:
        """Manually trigger or force an immediate congestion event."""
        self.congestion_delay_seconds = self.elapsed_sim_seconds
        if duration_seconds:
            self.congestion_duration_seconds = duration_seconds
        self.is_congested = True

    def generate_next_metric(self, step_seconds: float = 3.0) -> MetricEvent:
        """
        Advances virtual simulation clock and produces a canonical MetricEvent.
        """
        # Advance simulation time by step * speed_multiplier
        delta = step_seconds * self.speed_multiplier
        self.elapsed_sim_seconds += delta
        self.sim_time += timedelta(seconds=delta)

        # 1. Base seasonal factor (diurnal * weekend)
        diurnal = self.calculate_diurnal_factor(self.sim_time)
        weekend = self.calculate_weekend_factor(self.sim_time)
        seasonal_multiplier = diurnal * weekend

        # 2. Congestion event ramp calculation
        # If elapsed time is within the congestion window:
        # [congestion_delay, congestion_delay + congestion_duration]
        congestion_multiplier = 1.0
        congestion_progress = 0.0  # 0.0 (start) to 1.0 (peak)

        if self.elapsed_sim_seconds >= self.congestion_delay_seconds:
            time_into_congestion = self.elapsed_sim_seconds - self.congestion_delay_seconds
            if time_into_congestion < self.congestion_duration_seconds:
                self.is_congested = True
                # Normalized progress [0.0 -> 1.0]
                congestion_progress = time_into_congestion / self.congestion_duration_seconds
                # Gradual ramp-up using smooth S-curve
                ramp = (1.0 - math.cos(congestion_progress * math.pi)) / 2.0
                congestion_multiplier = 1.0 + (ramp * (self.congestion_severity - 1.0))
            elif time_into_congestion < (self.congestion_duration_seconds * 1.5):
                # Recovery phase
                recovery_progress = (time_into_congestion - self.congestion_duration_seconds) / (self.congestion_duration_seconds * 0.5)
                ramp = 1.0 - recovery_progress
                congestion_multiplier = 1.0 + (ramp * (self.congestion_severity - 1.0))
                congestion_progress = ramp
                self.is_congested = False
            else:
                self.is_congested = False

        # 3. Calculate Active Users with Noise
        noise_std = (self.noise_percent / 100.0) * self.base_users
        noise = random.gauss(0, noise_std)
        raw_users = (self.base_users * seasonal_multiplier * congestion_multiplier) + noise
        active_users = max(20, int(raw_users))

        # 4. Request Rate (RPS)
        # Typically ~0.3 - 0.4 requests/sec per active user under normal conditions
        user_rps_ratio = 0.35 + random.uniform(-0.03, 0.03)
        request_rate = max(1.0, round(active_users * user_rps_ratio, 2))

        # 5. Response Time & Error Rate Degradation Dynamics
        # Under normal conditions: latency ~35-50ms, error rate < 0.3%
        # When congestion starts (progress > 0.25):
        #   - Latency begins climbing steadily (early indicator)
        # When congestion nears peak (progress > 0.70):
        #   - Error rate surges exponentially (502/504 buffer saturation)
        base_latency = 38.0 + random.uniform(-4, 6)
        base_error = max(0.01, random.uniform(0.05, 0.25))

        if congestion_progress > 0.0:
            # Phase 1 & 2: Latency increases early as internal queue depths rise
            latency_degradation = (congestion_progress ** 1.6) * 450.0  # Can reach 500ms+
            avg_response_time = base_latency + latency_degradation

            # Phase 3: Error rate spikes late (after latency has degraded)
            if congestion_progress > 0.55:
                error_spike_progress = (congestion_progress - 0.55) / 0.45
                error_surge = (error_spike_progress ** 2.2) * 22.0  # Can reach 20%+
                error_rate = min(95.0, base_error + error_surge)
            else:
                error_rate = base_error + (congestion_progress * 0.5)
        else:
            avg_response_time = base_latency
            error_rate = base_error

        # Construct strictly validated canonical MetricEvent
        event = MetricEvent(
            site_id=self.site_id,
            timestamp=self.sim_time,
            active_users=active_users,
            request_rate=round(request_rate, 2),
            avg_response_time_ms=round(avg_response_time, 2),
            error_rate_percent=round(error_rate, 2),
        )
        return event
