"""Offline, review-only hydrology evidence.

No function in this package changes a locality mapping or an alert severity.
Outputs are evidence for hydrology review until a qualified reviewer explicitly
approves a relationship elsewhere.
"""

from .lag import analyze_relationship
from .pipeline import build_review, persist_review

__all__ = ["analyze_relationship", "build_review", "persist_review"]
