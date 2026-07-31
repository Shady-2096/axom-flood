"""Fail-closed parsing for cached CWC historical observations.

The CWC history endpoint can return more than one row for the same station and
hour. A later validation may also preserve the originally entered value beside a
corrected ``dataValidatedValue``. Picking the first row would make a travel-time
model depend on response ordering, while deduplicating only by timestamp would
silently discard corrections.

This module resolves an hour only when there is one unambiguous value:

* one validated value wins over any raw values for that hour;
* conflicting validated values make the hour unusable;
* without a validated value, conflicting raw values make the hour unusable.

Nothing here changes the live CWC alert path. It is deliberately limited to
offline historical analysis and records every rejection in an audit summary.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .client import LEVEL_DATATYPE, parse_ffs_time


@dataclass(frozen=True)
class Observation:
    """One resolved reduced-level observation."""

    observed_at: datetime
    level_m: float
    value_source: str


@dataclass(frozen=True)
class HistoryAudit:
    """Counts proving how a raw cached response became a resolved series."""

    rows_seen: int
    observations_accepted: int
    foreign_datatype_rows: int
    wrong_station_rows: int
    malformed_rows: int
    implausible_rows: int
    duplicate_rows_collapsed: int
    corrections_applied: int
    ambiguous_timestamps: int
    ambiguous_timestamp_examples: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "rows_seen": self.rows_seen,
            "observations_accepted": self.observations_accepted,
            "foreign_datatype_rows": self.foreign_datatype_rows,
            "wrong_station_rows": self.wrong_station_rows,
            "malformed_rows": self.malformed_rows,
            "implausible_rows": self.implausible_rows,
            "duplicate_rows_collapsed": self.duplicate_rows_collapsed,
            "corrections_applied": self.corrections_applied,
            "ambiguous_timestamps": self.ambiguous_timestamps,
            "ambiguous_timestamp_examples": list(self.ambiguous_timestamp_examples),
        }


@dataclass(frozen=True)
class HistorySeries:
    """Resolved history plus content identity and an audit trail."""

    station_code: str
    observations: tuple[Observation, ...]
    audit: HistoryAudit
    source_path: str
    source_sha256: str

    def provenance(self) -> dict[str, Any]:
        first = self.observations[0].observed_at.isoformat() if self.observations else None
        last = self.observations[-1].observed_at.isoformat() if self.observations else None
        return {
            "station_code": self.station_code,
            "source_path": self.source_path,
            "source_sha256": self.source_sha256,
            "first_observed_at": first,
            "last_observed_at": last,
            **self.audit.as_dict(),
        }


def _finite_number(value: Any) -> float | None:
    if value in (None, "") or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _plausible_history_value(observed_at: datetime, level_m: float) -> bool:
    """Apply only structural checks, never a statistical high-water ceiling."""

    return (
        level_m > 0
        and observed_at.minute == 0
        and observed_at.second == 0
        and observed_at.microsecond == 0
    )


def resolve_history_rows(
    rows: Iterable[dict[str, Any]],
    *,
    station_code: str,
    ambiguous_example_limit: int = 20,
) -> tuple[tuple[Observation, ...], HistoryAudit]:
    """Resolve raw CWC rows without silently choosing between corrections."""

    buckets: dict[datetime, dict[str, Any]] = {}
    rows_seen = 0
    foreign_datatype_rows = 0
    wrong_station_rows = 0
    malformed_rows = 0
    implausible_rows = 0

    for row in rows:
        rows_seen += 1
        identity = row.get("id")
        if not isinstance(identity, dict):
            malformed_rows += 1
            continue
        datatype = row.get("datatypeCode") or identity.get("datatypeCode")
        if datatype != LEVEL_DATATYPE:
            foreign_datatype_rows += 1
            continue
        row_station = row.get("stationCode") or identity.get("stationCode")
        if row_station != station_code:
            wrong_station_rows += 1
            continue
        try:
            observed_at = parse_ffs_time(str(identity["dataTime"]))
        except (KeyError, TypeError, ValueError):
            malformed_rows += 1
            continue

        raw_value = _finite_number(row.get("dataValue"))
        validated_present = row.get("dataValidatedValue") not in (None, "")
        validated_value = _finite_number(row.get("dataValidatedValue"))
        if validated_present and validated_value is None:
            malformed_rows += 1
            continue
        effective = validated_value if validated_value is not None else raw_value
        if effective is None:
            malformed_rows += 1
            continue
        if not _plausible_history_value(observed_at, effective):
            implausible_rows += 1
            continue

        bucket = buckets.setdefault(
            observed_at,
            {
                "validated": set(),
                "raw": set(),
                "row_count": 0,
                "correction_seen": False,
            },
        )
        bucket["row_count"] += 1
        if validated_value is not None:
            bucket["validated"].add(validated_value)
            if raw_value is not None:
                bucket["raw"].add(raw_value)
                if raw_value != validated_value:
                    bucket["correction_seen"] = True
        elif raw_value is not None:
            bucket["raw"].add(raw_value)

    observations: list[Observation] = []
    duplicate_rows_collapsed = 0
    corrections_applied = 0
    ambiguous: list[str] = []

    for observed_at, bucket in sorted(buckets.items()):
        validated = bucket["validated"]
        raw = bucket["raw"]
        if len(validated) > 1 or (not validated and len(raw) > 1):
            ambiguous.append(observed_at.isoformat())
            continue
        if validated:
            level_m = next(iter(validated))
            value_source = "validated"
            if bucket["correction_seen"] or any(value != level_m for value in raw):
                corrections_applied += 1
        elif raw:
            level_m = next(iter(raw))
            value_source = "raw"
        else:  # Defensive: accepted input always put a value in one set.
            continue
        duplicate_rows_collapsed += max(0, int(bucket["row_count"]) - 1)
        observations.append(
            Observation(
                observed_at=observed_at,
                level_m=level_m,
                value_source=value_source,
            )
        )

    audit = HistoryAudit(
        rows_seen=rows_seen,
        observations_accepted=len(observations),
        foreign_datatype_rows=foreign_datatype_rows,
        wrong_station_rows=wrong_station_rows,
        malformed_rows=malformed_rows,
        implausible_rows=implausible_rows,
        duplicate_rows_collapsed=duplicate_rows_collapsed,
        corrections_applied=corrections_applied,
        ambiguous_timestamps=len(ambiguous),
        ambiguous_timestamp_examples=tuple(ambiguous[:ambiguous_example_limit]),
    )
    return tuple(observations), audit


def load_cached_history(path: Path, *, station_code: str | None = None) -> HistorySeries:
    """Load one raw cached endpoint body and retain its content identity."""

    body = path.read_bytes()
    payload = json.loads(body)
    if not isinstance(payload, list):
        raise ValueError(f"CWC history cache must contain a JSON array: {path}")
    code = station_code or path.stem
    observations, audit = resolve_history_rows(payload, station_code=code)
    return HistorySeries(
        station_code=code,
        observations=observations,
        audit=audit,
        source_path=str(path),
        source_sha256=hashlib.sha256(body).hexdigest(),
    )


__all__ = [
    "HistoryAudit",
    "HistorySeries",
    "Observation",
    "load_cached_history",
    "resolve_history_rows",
]
