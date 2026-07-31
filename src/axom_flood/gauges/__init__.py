"""Hourly gauge ingestion and snapshot derivation."""

from .pipeline import ingest_gauge_csv

__all__ = ["ingest_gauge_csv"]
