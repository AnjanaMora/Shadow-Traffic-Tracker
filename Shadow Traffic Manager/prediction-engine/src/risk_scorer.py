"""
Shadow Traffic — Congestion Risk Scorer & ETA Estimator
Role in Architecture:
    Combines seasonal baseline deviations and ML forward forecasts into a calibrated
    0–100 Congestion Risk Score. Provides explainable metric factor attribution
    and estimates time-to-congestion (ETA) via linear trend velocity extrapolation.
"""

import math
import logging
from typing import Dict, List, Optional, Tuple
import numpy as np

from shadow_shared.models import MetricEvent
from .config import settings
from .models import ContributingFactor, ForecastInterval, RiskStatus

logger = logging.getLogger("prediction.risk_scorer")


class RiskScorer:
    """
    Evaluates multi-factor congestion risk, classifies operational status,
    identifies primary bottlenecks, and extrapolates time-to-congestion.
    """

    def __init__(
        self,
        weights: Dict[str, float] = settings.METRIC_WEIGHTS,
        critical_thresholds: Dict[str, float] = settings.CRITICAL_THRESHOLDS,
        max_eta_minutes: float = settings.MAX_ETA_MINUTES,
    ):
        self.weights = weights
        self.critical_thresholds = critical_thresholds
        self.max_eta_minutes = max_eta_minutes

    def calculate_risk(
        self,
        current_metric: MetricEvent,
        baselines: Dict[str, Tuple[float, float]],
        forecasts: Dict[str, ForecastInterval],
        recent_window: Optional[List[MetricEvent]] = None,
    ) -> Tuple[float, RiskStatus, Optional[float], Optional[str], List[ContributingFactor], str]:
        """
        Calculates 0–100 Congestion Risk Score, status, ETA, and explainable factors.
        Returns: (score, status, eta_minutes, primary_bottleneck, contributing_factors, recommendation)
        """
        metrics_current = {
            "avg_response_time_ms": current_metric.avg_response_time_ms,
            "error_rate_percent": current_metric.error_rate_percent,
            "request_rate": current_metric.request_rate,
            "active_users": float(current_metric.active_users),
        }

        sub_scores: Dict[str, float] = {}
        z_scores: Dict[str, float] = {}
        contributing_factors: List[ContributingFactor] = []

        total_weighted_score = 0.0

        for metric_name, curr_val in metrics_current.items():
            mean, std = baselines.get(metric_name, (curr_val, 1.0))
            forecast = forecasts.get(metric_name)
            yhat = forecast.yhat if forecast else curr_val
            yhat_upper = forecast.yhat_upper if forecast else curr_val

            # 1. Deviation from seasonal baseline (Z-Score)
            safe_std = max(settings.MIN_STD_FLOOR, std)
            z = (curr_val - mean) / safe_std
            z_scores[metric_name] = round(z, 2)

            # Deviation score component: z=0 -> 0, z=2.0 -> 40, z=3.5 -> 70, z>=5.0 -> 100
            current_dev_score = float(np.clip(max(0.0, z) * 20.0, 0.0, 100.0))

            # 2. Forecast Trend vs Upper Baseline Bound (mean + 2*std)
            upper_baseline = mean + (2.0 * safe_std)
            if yhat_upper > upper_baseline:
                forecast_excess = (yhat_upper - upper_baseline) / safe_std
                forecast_risk_score = float(np.clip(forecast_excess * 25.0, 0.0, 100.0))
            else:
                forecast_risk_score = 0.0

            # Composite sub-score for this metric
            metric_score = (0.55 * current_dev_score) + (0.45 * forecast_risk_score)

            # Hard SLA override: if critical threshold breached directly, jump to 100
            crit_threshold = self.critical_thresholds.get(metric_name)
            if crit_threshold and curr_val >= crit_threshold:
                metric_score = 100.0

            sub_scores[metric_name] = metric_score
            weight = self.weights.get(metric_name, 0.25)
            total_weighted_score += weight * metric_score

        final_score = round(float(np.clip(total_weighted_score, 0.0, 100.0)), 1)

        # Classify status
        if final_score >= 80.0:
            status = RiskStatus.CRITICAL
        elif final_score >= 60.0:
            status = RiskStatus.WARNING
        elif final_score >= 40.0:
            status = RiskStatus.WATCH
        else:
            status = RiskStatus.NORMAL

        # 3. Explainable Factor Attribution
        total_raw_impact = sum(self.weights[m] * sub_scores[m] for m in metrics_current)
        sorted_metrics = sorted(
            metrics_current.keys(),
            key=lambda m: self.weights[m] * sub_scores[m],
            reverse=True,
        )

        primary_bottleneck = sorted_metrics[0] if total_raw_impact > 5.0 else None

        for m in sorted_metrics:
            impact = self.weights[m] * sub_scores[m]
            pct_contrib = round((impact / total_raw_impact * 100.0), 1) if total_raw_impact > 0 else 25.0
            mean, std = baselines[m]
            fc = forecasts.get(m)
            fc_val = fc.yhat if fc else metrics_current[m]
            z = z_scores[m]

            # Generate natural language reason
            if z > 3.0:
                reason = f"Severe surge: +{z:.1f}σ above expected seasonal norm ({mean:.1f})"
            elif z > 1.5:
                reason = f"Elevated load: +{z:.1f}σ above expected seasonal norm ({mean:.1f})"
            elif z < -1.0:
                reason = f"Below seasonal baseline ({mean:.1f})"
            else:
                reason = "Running within healthy seasonal baseline boundaries"

            contributing_factors.append(
                ContributingFactor(
                    metric=m,
                    current_value=round(metrics_current[m], 2),
                    baseline_mean=mean,
                    baseline_std=std,
                    z_score=z,
                    forecast_value=round(fc_val, 2),
                    percentage_contribution=pct_contrib,
                    reason=reason,
                )
            )

        # 4. Time-to-Congestion (ETA) Estimation
        eta_minutes = self._estimate_time_to_congestion(
            primary_bottleneck=primary_bottleneck,
            current_metric=current_metric,
            recent_window=recent_window,
        )

        # 5. Recommendation
        recommendation = self._generate_recommendation(status, primary_bottleneck, eta_minutes)

        return (
            final_score,
            status,
            eta_minutes,
            primary_bottleneck,
            contributing_factors,
            recommendation,
        )

    def _estimate_time_to_congestion(
        self,
        primary_bottleneck: Optional[str],
        current_metric: MetricEvent,
        recent_window: Optional[List[MetricEvent]],
    ) -> Optional[float]:
        """
        Extrapolates linear velocity (dx/dt) of the primary bottleneck metric
        to estimate minutes until it breaches the critical SLA threshold.
        Sanity-capped at max_eta_minutes (120 minutes / 2 hours).
        """
        if not primary_bottleneck or not recent_window or len(recent_window) < 3:
            return None

        crit_threshold = self.critical_thresholds.get(primary_bottleneck)
        if not crit_threshold:
            return None

        # Extract chronological values and timestamps
        sorted_window = sorted(recent_window, key=lambda e: e.timestamp)
        t0 = sorted_window[0].timestamp

        times_min = np.array(
            [(e.timestamp - t0).total_seconds() / 60.0 for e in sorted_window]
        )
        values = np.array([getattr(e, primary_bottleneck) for e in sorted_window])

        curr_val = values[-1]
        if curr_val >= crit_threshold:
            return 0.0  # Already breached

        # Compute trend slope per minute (velocity)
        if len(times_min) > 1 and (times_min[-1] - times_min[0]) > 0.05:
            slope, _ = np.polyfit(times_min, values, 1)
        else:
            slope = 0.0

        # If slope is flat or downward, there is no congestion collision trajectory
        if slope <= 0.001:
            return None

        # Extrapolate: delta_to_breach / slope
        delta = crit_threshold - curr_val
        eta = delta / slope

        # Sanity cap: reject nonsensical multi-day extrapolations
        if eta > self.max_eta_minutes:
            return None

        return round(float(eta), 1)

    @staticmethod
    def _generate_recommendation(
        status: RiskStatus, primary_bottleneck: Optional[str], eta_minutes: Optional[float]
    ) -> str:
        if status == RiskStatus.CRITICAL:
            eta_str = f" Breach imminent in {eta_minutes:.0f}m." if eta_minutes else ""
            return (
                f"CRITICAL:{eta_str} Primary bottleneck on '{primary_bottleneck}'. "
                f"Activate automated circuit breakers, shed non-critical traffic, and scale capacity."
            )
        elif status == RiskStatus.WARNING:
            eta_str = f" Critical saturation projected in ~{eta_minutes:.0f}m." if eta_minutes else ""
            return (
                f"WARNING:{eta_str} Upward congestion velocity detected on '{primary_bottleneck}'. "
                f"Trigger auto-scaling warmup and enable CDN edge caching."
            )
        elif status == RiskStatus.WATCH:
            return (
                f"WATCH: Minor seasonal divergence detected on '{primary_bottleneck}'. "
                f"Monitoring queue depths and latency drift."
            )
        else:
            return "NORMAL: All metrics operating comfortably within seasonal baselines."
