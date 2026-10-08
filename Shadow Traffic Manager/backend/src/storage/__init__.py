"""
Shadow Traffic — Storage Package
Role in Architecture:
    TimescaleDB storage engine package providing the Data Access Layer (DAL),
    hypertable schema definitions, continuous aggregates, and seed scripts.
"""

from .dal import TimescaleDAL
from .models import MetricRollup

__all__ = ["TimescaleDAL", "MetricRollup"]
