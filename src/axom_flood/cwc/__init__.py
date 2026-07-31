"""CWC Flood Forecasting System gauge feed."""

from .client import FfsClient, parse_ffs_time
from .pipeline import gauge_id_for, ingest_cwc_gauges

__all__ = ["FfsClient", "gauge_id_for", "ingest_cwc_gauges", "parse_ffs_time"]
