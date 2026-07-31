"""UDISE school reference ingest and camp matching."""

from .ingest import DEFAULT_SOURCE_URL, ingest_assam_schools
from .matcher import match_camps_to_schools

__all__ = ["DEFAULT_SOURCE_URL", "ingest_assam_schools", "match_camps_to_schools"]
