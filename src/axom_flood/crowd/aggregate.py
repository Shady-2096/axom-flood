"""Display rules for crowd reports.

Three rules from ``assam-flood-implementation-plan.md`` PART 4 §2.3, enforced
here so the published open dataset never presents a single report as fact:

* ``aggregate_statements`` &mdash; grouped counts like ``"3 people reported
  knee-deep water near Nazira Town within the last hour"``. A single report
  never reaches display.
* ``decay`` &mdash; reports fade over six hours and are hidden after 12
  during an active event.
* ``contradiction_flag`` &mdash; a report that disagrees with its neighbours
  at the same cell and time is flagged for review and never auto-deleted.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

#: Reports fade to zero display confidence over this many hours.
DECAY_HOURS = 6
#: Hard hide during an active event past this many hours.
HIDE_HOURS = 12

_WET = ("ankle", "knee", "waist_plus")
_DRY = "dry"


def age_hours(report: dict[str, Any], *, now: datetime) -> float:
    submitted = datetime.fromisoformat(report["submitted_at"])
    if submitted.tzinfo is None:
        submitted = submitted.replace(tzinfo=IST)
    return max(0.0, (now - submitted).total_seconds() / 3600.0)


def display_confidence(report: dict[str, Any], *, now: datetime) -> float:
    """Linear fade from 1 at submission to 0 at ``DECAY_HOURS``."""
    return max(0.0, 1.0 - age_hours(report, now=now) / DECAY_HOURS)


def is_visible(report: dict[str, Any], *, now: datetime, active_event: bool) -> bool:
    age = age_hours(report, now=now)
    return not (active_event and age > HIDE_HOURS)


def _place_name(report: dict[str, Any], localities: dict[str, dict[str, Any]]) -> str:
    locality = localities.get(report.get("locality_id") or "")
    if locality:
        return locality.get("revenue_circle") or locality.get("name_en") or "your area"
    lon, lat = report["location"]
    return f"near {lat:.3f},{lon:.3f}"


_DEPTH_WORDS = {
    "dry": "dry ground",
    "ankle": "ankle-deep water",
    "knee": "knee-deep water",
    "waist_plus": "waist-deep or higher water",
}


def aggregate_statements(
    reports: list[dict[str, Any]],
    *,
    now: datetime,
    localities: dict[str, dict[str, Any]],
    within_hours: int = 1,
) -> list[dict[str, Any]]:
    """Collapse reports into ``N people reported D near P within the last hour``.

    A single report never produces a public statement. Groups of fewer than
    two are returned to the private reconciliation step with ``quorum=false``
    so operators can count withheld groups without publishing their location.
    """
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for report in reports:
        age = age_hours(report, now=now)
        if age > within_hours:
            continue
        place = _place_name(report, localities)
        groups[(place, report["depth_class"])].append(report)

    statements: list[dict[str, Any]] = []
    for (place, depth), members in sorted(groups.items()):
        statements.append(
            {
                "place": place,
                "depth_class": depth,
                "depth_phrase_en": _DEPTH_WORDS.get(depth, depth),
                "count": len(members),
                "within_hours": within_hours,
                "quorum": len(members) >= 2,
            }
        )
    statements.sort(key=lambda item: (-item["count"], item["place"], item["depth_class"]))
    return statements


def flag_contradictions(reports: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Mark reports that disagree with neighbours at the same cell and time.

    Two reports within the same rounded cell and a 30-minute window that
    span ``dry`` and any wet depth class are flagged
    ``neighbour_contradiction`` for human review. They are never deleted.
    """
    by_cell: dict[tuple[float, float], list[dict[str, Any]]] = defaultdict(list)
    for report in reports:
        lon, lat = report["location"]
        by_cell[(round(lon, 3), round(lat, 3))].append(report)

    flagged: list[dict[str, Any]] = []
    for members in by_cell.values():
        members = sorted(members, key=lambda r: r["submitted_at"])
        for i, current in enumerate(members):
            t0 = datetime.fromisoformat(current["submitted_at"])
            if t0.tzinfo is None:
                t0 = t0.replace(tzinfo=IST)
            for other in members[i + 1:]:
                t1 = datetime.fromisoformat(other["submitted_at"])
                if t1.tzinfo is None:
                    t1 = t1.replace(tzinfo=IST)
                if abs((t1 - t0).total_seconds()) > 1800:
                    continue
                a_dry = current["depth_class"] == _DRY
                b_dry = other["depth_class"] == _DRY
                a_wet = current["depth_class"] in _WET
                b_wet = other["depth_class"] in _WET
                contradicts = (a_dry and b_wet) or (a_wet and b_dry)
                if not contradicts:
                    continue
                for report in (current, other):
                    if "neighbour_contradiction" not in report["flags"]:
                        report["flags"].append("neighbour_contradiction")
                        flagged.append(report)
    return flagged


def reconcile_dataset(
    reports: list[dict[str, Any]],
    *,
    now: datetime,
    localities: dict[str, dict[str, Any]],
    active_event: bool = False,
) -> dict[str, Any]:
    """Apply decay, hide, and return an aggregate-only public document.

    The append-only series is the private review surface. Public artifacts
    deliberately contain no report IDs, device hashes, coordinates, per-report
    confidence values, or below-quorum place names.
    """
    visible = [
        report
        for report in reports
        if is_visible(report, now=now, active_event=active_event)
    ]
    flag_contradictions(visible)
    statements = aggregate_statements(visible, now=now, localities=localities)
    public_statements = [statement for statement in statements if statement["quorum"]]
    return {
        "schema_version": 2,
        "generated_at": now.isoformat(),
        "active_event": active_event,
        "privacy_scope": "aggregate_only",
        "report_count_total": len(reports),
        "report_count_visible": len(visible),
        "report_count_hidden_after_event": len(reports) - len(visible),
        "below_quorum_group_count": sum(not statement["quorum"] for statement in statements),
        "contradictions_flagged_count": sum(
            "neighbour_contradiction" in report["flags"] for report in visible
        ),
        "aggregate_statements": public_statements,
    }


def load_locality_index(localities_path: Path) -> dict[str, dict[str, Any]]:
    if not localities_path.exists():
        return {}
    document = json.loads(localities_path.read_text())
    return {
        str(item.get("locality_id")): item
        for item in document.get("localities", [])
        if item.get("locality_id")
    }


__all__ = [
    "DECAY_HOURS",
    "HIDE_HOURS",
    "aggregate_statements",
    "display_confidence",
    "flag_contradictions",
    "is_visible",
    "load_locality_index",
    "reconcile_dataset",
]
