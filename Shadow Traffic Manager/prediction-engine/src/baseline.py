"""
Shadow Traffic — Seasonal Baseline Model
Role in Architecture:
    Calculates time-slot seasonal baselines grouped by (day_of_week, hour_of_day)
    across the 4 canonical metrics (active_users, request_rate, avg_response_time_ms,
    error_rate_percent). Applies EWMA to weight recent weeks over distant history.
"""

import math
import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from shadow_shared.models import MetricEvent
from .config import settings

logger = logging.getLogger("prediction.baseline")


class SeasonalBaselineModel:
    """
    Seasonal baseline model partitioning time into 168 weekly slots:
    (day_of_week in [0..6], hour_of_day in [0..23]).
    Maintains exponentially-weighted moving averages (EWMA) of mean and standard deviation.
    """

    def __init__(self, alpha: float = settings.BASELINE_EWMA_ALPHA, min_std_floor: float = settings.MIN_STD_FLOOR):
        self.alpha = alpha
        self.min_std_floor = min_std_floor
        # Structure: baselines[site_id][metric][(dow, hour)] = (mean, std, sample_count)
        self.baselines: Dict[str, Dict[str, Dict[Tuple[int, int], Tuple[float, float, int]]]] = defaultdict(
            lambda: defaultdict(dict)
        )

    def fit_events(self, site_id: str, events: List[MetricEvent]) -> None:
        """
        Batch update the seasonal baseline using a list of historical MetricEvents.
        Events are processed in chronological order to apply EWMA weighting.
        """
        sorted_events = sorted(events, key=lambda e: e.timestamp)
        for ev in sorted_events:
            self.update_single(ev)

    def update_single(self, event: MetricEvent) -> None:
        """
        Incrementally update the baseline for the event's site_id and time slot.
        """
        site_id = event.site_id
        dow = event.timestamp.weekday()  # 0=Monday, 6=Sunday
        hour = event.timestamp.hour      # 0..23
        slot = (dow, hour)

        metrics_map = {
            "active_users": float(event.active_users),
            "request_rate": float(event.request_rate),
            "avg_response_time_ms": float(event.avg_response_time_ms),
            "error_rate_percent": float(event.error_rate_percent),
        }

        for metric_name, val in metrics_map.items():
            current_entry = self.baselines[site_id][metric_name].get(slot)
            if current_entry is None:
                # First observation in this time slot
                # Initialize std with a reasonable default fraction of mean
                initial_std = max(self.min_std_floor, val * 0.15)
                self.baselines[site_id][metric_name][slot] = (val, initial_std, 1)
            else:
                old_mean, old_std, count = current_entry
                # Adaptive EWMA: if low count, use higher learning rate for fast convergence
                eff_alpha = self.alpha if count >= 10 else (1.0 / (count + 1))
                new_mean = (eff_alpha * val) + ((1.0 - eff_alpha) * old_mean)

                # Variance update
                var_diff = (val - new_mean) ** 2
                old_var = old_std ** 2
                new_var = (eff_alpha * var_diff) + ((1.0 - eff_alpha) * old_var)
                new_std = max(self.min_std_floor, math.sqrt(max(0.0, new_var)))

                self.baselines[site_id][metric_name][slot] = (new_mean, new_std, count + 1)

    def get_baseline(
        self, site_id: str, metric: str, timestamp: datetime
    ) -> Tuple[float, float]:
        """
        Retrieve expected (mean, std) for a given site, metric, and timestamp.
        Returns: (expected_mean, expected_std)
        """
        dow = timestamp.weekday()
        hour = timestamp.hour
        slot = (dow, hour)

        entry = self.baselines[site_id][metric].get(slot)
        if entry is not None:
            mean, std, _ = entry
            return round(mean, 2), round(max(self.min_std_floor, std), 2)

        # Cold-start fallback: compute heuristic diurnal baseline if slot unobserved
        return self._generate_cold_start_baseline(metric, dow, hour)

    def _generate_cold_start_baseline(self, metric: str, dow: int, hour: int) -> Tuple[float, float]:
        """
        Synthesizes an organic diurnal baseline when no historical observations exist
        for a specific (day_of_week, hour_of_day) slot.
        """
        # Diurnal curve peaking at 14:00 (2pm)
        angle = ((hour - 14.0) / 24.0) * 2.0 * math.pi
        curve = (math.cos(angle) + 1.0) / 2.0  # [0.0, 1.0]
        diurnal_factor = 0.40 + (curve * 1.20) # [0.40, 1.60]
        weekend_factor = 0.85 if dow >= 5 else 1.0
        scale = diurnal_factor * weekend_factor

        if metric == "active_users":
            mean = 800.0 * scale
            std = max(20.0, mean * 0.15)
        elif metric == "request_rate":
            mean = (800.0 * scale) * 0.35
            std = max(10.0, mean * 0.15)
        elif metric == "avg_response_time_ms":
            mean = 40.0 + (scale * 8.0)
            std = max(3.0, mean * 0.12)
        elif metric == "error_rate_percent":
            mean = 0.15
            std = 0.10
        else:
            mean = 100.0
            std = 15.0

        return round(mean, 2), round(std, 2)
