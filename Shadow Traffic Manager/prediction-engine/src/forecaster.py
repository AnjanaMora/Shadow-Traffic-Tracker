"""
Shadow Traffic — Dual Forecasting Engine (Prophet + Statsmodels)
Role in Architecture:
    Produces forward-looking metric forecasts (15–30 minutes) with calibrated
    confidence intervals (yhat, yhat_lower, yhat_upper). Selects between
    Facebook Prophet (for extensive multi-observation history) and Statsmodels
    linear/exponential decomposition (for shorter windows or fast path).
"""

import logging
import math
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Tuple
import numpy as np
import pandas as pd

from .config import settings
from .models import ForecastInterval

logger = logging.getLogger("prediction.forecaster")

# Attempt Prophet import
try:
    from prophet import Prophet
    PROPHET_AVAILABLE = True
except ImportError:
    PROPHET_AVAILABLE = False
    logger.warning("Facebook Prophet not available; defaulting to statsmodels engine.")

# Attempt statsmodels import
try:
    import statsmodels.api as sm
    STATSMODELS_AVAILABLE = True
except ImportError:
    STATSMODELS_AVAILABLE = False
    logger.warning("Statsmodels not available; defaulting to linear regression.")


class DualForecaster:
    """
    Forecasting engine dynamically selecting Prophet or Statsmodels
    based on sample size and execution constraints.
    """

    def __init__(
        self,
        horizon_minutes: int = settings.FORECAST_HORIZON_MINUTES,
        confidence_level: float = settings.CONFIDENCE_LEVEL,
        min_prophet_samples: int = settings.MIN_PROPHET_SAMPLES,
    ):
        self.horizon_minutes = horizon_minutes
        self.confidence_level = confidence_level
        self.min_prophet_samples = min_prophet_samples

    def forecast(
        self,
        metric_name: str,
        series: List[Tuple[datetime, float]],
        horizon_minutes: Optional[int] = None,
    ) -> ForecastInterval:
        """
        Produce a forward forecast with confidence bounds.
        series: chronological list of (timestamp, value) tuples.
        """
        h_mins = horizon_minutes or self.horizon_minutes

        if not series:
            return ForecastInterval(
                metric_name=metric_name,
                horizon_minutes=h_mins,
                yhat=0.0,
                yhat_lower=0.0,
                yhat_upper=0.0,
                confidence_level=self.confidence_level,
                model_used="none",
            )

        # 1. Single or two-point fallback
        if len(series) < 3:
            return self._forecast_persistence(metric_name, series, h_mins)

        # 2. Large dataset: attempt Prophet
        if PROPHET_AVAILABLE and len(series) >= self.min_prophet_samples:
            try:
                return self._forecast_prophet(metric_name, series, h_mins)
            except Exception as exc:
                logger.debug(f"Prophet failed for {metric_name} ({exc}); falling back to statsmodels.")

        # 3. Statsmodels engine
        return self._forecast_statsmodels(metric_name, series, h_mins)

    def _forecast_prophet(
        self, metric_name: str, series: List[Tuple[datetime, float]], horizon_minutes: int
    ) -> ForecastInterval:
        """Fit Prophet model and extrapolate with confidence intervals."""
        df = pd.DataFrame(series, columns=["ds", "y"])
        # Remove timezone info for Prophet compatibility
        if df["ds"].dt.tz is not None:
            df["ds"] = df["ds"].dt.tz_localize(None)

        # Configure Prophet with minimal logging
        m = Prophet(
            interval_width=self.confidence_level,
            daily_seasonality=True,
            weekly_seasonality=len(series) >= 200,
            yearly_seasonality=False,
        )
        # Suppress verbose output
        logging.getLogger("prophet").setLevel(logging.WARNING)
        logging.getLogger("cmdstanpy").setLevel(logging.WARNING)

        m.fit(df)

        future = m.make_future_dataframe(periods=horizon_minutes, freq="min")
        forecast_df = m.predict(future)

        target_row = forecast_df.iloc[-1]
        yhat = max(0.0, float(target_row["yhat"]))
        yhat_lower = max(0.0, float(target_row["yhat_lower"]))
        yhat_upper = max(yhat_lower, float(target_row["yhat_upper"]))

        return ForecastInterval(
            metric_name=metric_name,
            horizon_minutes=horizon_minutes,
            yhat=round(yhat, 2),
            yhat_lower=round(yhat_lower, 2),
            yhat_upper=round(yhat_upper, 2),
            confidence_level=self.confidence_level,
            model_used="prophet",
        )

    def _forecast_statsmodels(
        self, metric_name: str, series: List[Tuple[datetime, float]], horizon_minutes: int
    ) -> ForecastInterval:
        """
        Statsmodels linear trend decomposition with student-t prediction intervals.
        """
        n = len(series)
        times = np.array([(s[0] - series[0][0]).total_seconds() / 60.0 for s in series])
        y = np.array([s[1] for s in series])

        # Forward target time in minutes from start
        target_t = times[-1] + horizon_minutes

        if STATSMODELS_AVAILABLE:
            X = sm.add_constant(times)
            model = sm.OLS(y, X).fit()
            X_pred = np.array([[1.0, target_t]])
            predictions = model.get_prediction(X_pred)
            pred_summary = predictions.summary_frame(alpha=1.0 - self.confidence_level)

            yhat = max(0.0, float(pred_summary["mean"].iloc[0]))
            yhat_lower = max(0.0, float(pred_summary["obs_ci_lower"].iloc[0]))
            yhat_upper = max(yhat_lower, float(pred_summary["obs_ci_upper"].iloc[0]))
        else:
            # Pure numpy linear regression fallback with analytical prediction interval
            slope, intercept = np.polyfit(times, y, 1)
            yhat = max(0.0, float(intercept + (slope * target_t)))

            # Estimate standard error of residuals
            residuals = y - (intercept + slope * times)
            s_err = math.sqrt(np.sum(residuals ** 2) / max(1, n - 2))

            # 90% confidence z multiplier ~ 1.645
            margin = 1.645 * s_err * math.sqrt(1 + (1.0 / n) + (((target_t - np.mean(times)) ** 2) / np.sum((times - np.mean(times)) ** 2)))
            yhat_lower = max(0.0, yhat - margin)
            yhat_upper = max(yhat_lower, yhat + margin)

        return ForecastInterval(
            metric_name=metric_name,
            horizon_minutes=horizon_minutes,
            yhat=round(yhat, 2),
            yhat_lower=round(yhat_lower, 2),
            yhat_upper=round(yhat_upper, 2),
            confidence_level=self.confidence_level,
            model_used="statsmodels",
        )

    def _forecast_persistence(
        self, metric_name: str, series: List[Tuple[datetime, float]], horizon_minutes: int
    ) -> ForecastInterval:
        """Zero-order persistence forecast for cold start."""
        last_val = series[-1][1]
        spread = max(1.0, last_val * 0.15)
        return ForecastInterval(
            metric_name=metric_name,
            horizon_minutes=horizon_minutes,
            yhat=round(last_val, 2),
            yhat_lower=round(max(0.0, last_val - spread), 2),
            yhat_upper=round(last_val + spread, 2),
            confidence_level=self.confidence_level,
            model_used="persistence",
        )
