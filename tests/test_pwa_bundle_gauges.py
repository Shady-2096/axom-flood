"""Which gauges reach the map.

CWC publishes retired stations beside live ones and retires them in batches: 44
Assam-region gauges last reported on 2025-04-29 or 2025-04-30, and five froze on
2022-10-12 under codes duplicating stations that are still live. Drawing those
puts permanently blank pins on the map, some of them beside a working gauge.
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
NOW = datetime(2026, 7, 30, 12, 0, tzinfo=IST)

_spec = importlib.util.spec_from_file_location(
    "build_pwa_bundle",
    Path(__file__).resolve().parents[1] / "scripts" / "build_pwa_bundle.py",
)
assert _spec and _spec.loader
_bundle = importlib.util.module_from_spec(_spec)
sys.modules["build_pwa_bundle"] = _bundle
_spec.loader.exec_module(_bundle)


def _gauge(observed_at: datetime | None) -> dict:
    return {"observed_at": observed_at.isoformat() if observed_at else None}


def test_a_reporting_gauge_is_published() -> None:
    assert _bundle._retired_from_service(_gauge(NOW - timedelta(hours=2)), now=NOW) is False


def test_a_gauge_quiet_for_a_few_days_is_still_published() -> None:
    """A manual gauge read by an observer, or an ordinary telemetry outage."""
    assert _bundle._retired_from_service(_gauge(NOW - timedelta(days=40)), now=NOW) is False


def test_a_gauge_silent_for_over_a_year_is_withheld() -> None:
    """The 2025-04-30 batch, fifteen months quiet."""
    assert _bundle._retired_from_service(_gauge(NOW - timedelta(days=456)), now=NOW) is True


def test_the_boundary_is_inclusive_of_a_year() -> None:
    assert _bundle._retired_from_service(_gauge(NOW - timedelta(days=365)), now=NOW) is False
    assert _bundle._retired_from_service(_gauge(NOW - timedelta(days=366)), now=NOW) is True


def test_a_gauge_that_has_never_reported_is_kept() -> None:
    """No history is not evidence of retirement — it may have just been added."""
    assert _bundle._retired_from_service(_gauge(None), now=NOW) is False
