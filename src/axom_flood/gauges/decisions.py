"""The reviewed gauge-topology decisions, and the one place they are applied.

Workstream 1 of the local-accuracy master plan. `scripts/build_gauge_decision_packets.py`
assembles the evidence for a person; this module holds what that person decided
and turns it into a mapping.

Why this is separate from the distance audit
--------------------------------------------

The distance audit can only demote. That property is load-bearing and is not
touched here: a machine measuring kilometres has no idea which river drains a
circle, so it must never be able to call a mapping reviewed. But it also means
the audit permanently demotes the *correct* answers — a gauge 80 km downstream
on your own river is right, and gets demoted every night regardless.

A reviewed decision is the other direction, and only a person can make one. The
reviewer sees the distance in their packet before deciding, so a decision that
keeps a far gauge has already answered the audit's objection. That is why a
reviewed circle skips the demotion instead of arguing with it. The geometry
facts stay on the record either way — `far` and `much_nearer_gauge_exists`
remain true, because they remain true.

Three outcomes, all first-class
-------------------------------

- ``keep`` — the assigned gauge sits on water that reaches this circle.
- ``reassign`` — a different gauge does; the decision names it.
- ``no_suitable_gauge_exists`` — nothing on this circle's drainage is gauged.
  The circle then carries no gauge at all and says so. That is better than
  quietly borrowing a number from the wrong river, which is the failure this
  whole workstream exists to end.

Qualification, recorded honestly
--------------------------------

``reviewer_qualification`` is free text and is stored verbatim. Someone who
knows Assam's rivers can answer these questions; a hydrologist is not required
and must not be implied. Whatever the reviewer's real qualification is, it
travels with every mapping it decided.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

#: The decision vocabulary, matching `scripts/build_gauge_decision_packets.py`.
ALLOWED_DECISIONS = ("keep", "reassign", "no_suitable_gauge_exists")

#: Set on every mapping this module writes, so a reviewed mapping is tellable
#: from one that came out of the hand-maintained override table.
REVIEWED_METHOD = "reviewed_river_topology"

#: What a reviewed circle with no gauge claims. Not "unverified" — nothing is
#: waiting to be verified — and not "high", which would read as confidence in a
#: reading that does not exist.
NO_GAUGE_CONFIDENCE = "not_applicable"

_REQUIRED = (
    "locality_id",
    "decision",
    "basis",
    "decision_reasoning",
    "reviewer",
    "reviewer_qualification",
    "reviewed_at",
)


class DecisionError(ValueError):
    """A decision record that cannot be applied without guessing at intent."""


@dataclass(frozen=True)
class Decision:
    """One reviewed answer for one revenue circle."""

    locality_id: str
    decision: str
    basis: str
    decision_reasoning: str
    reviewer: str
    reviewer_qualification: str
    reviewed_at: str
    primary_gauge: str | None = None

    @property
    def drops_the_gauge(self) -> bool:
        return self.decision == "no_suitable_gauge_exists"


def load(path: Path) -> dict[str, Decision]:
    """Read the reviewed record, keyed by locality.

    Raises rather than skipping. A decision that cannot be read is a decision
    someone made and this build silently ignored, which is worse than stopping.
    """
    if not path.exists():
        return {}
    document = json.loads(path.read_text())
    decisions: dict[str, Decision] = {}
    for row in document.get("decisions", []):
        missing = [field for field in _REQUIRED if not row.get(field)]
        if missing:
            raise DecisionError(
                f"{row.get('locality_id') or '<no locality_id>'}: missing "
                f"{', '.join(missing)}"
            )
        if row["decision"] not in ALLOWED_DECISIONS:
            raise DecisionError(
                f"{row['locality_id']}: decision {row['decision']!r} is not one of "
                f"{', '.join(ALLOWED_DECISIONS)}"
            )
        if row["locality_id"] in decisions:
            raise DecisionError(f"{row['locality_id']}: decided twice")
        if row["decision"] == "reassign" and not row.get("primary_gauge"):
            raise DecisionError(
                f"{row['locality_id']}: a reassign must name the gauge to read instead"
            )
        if row["decision"] == "no_suitable_gauge_exists" and row.get("primary_gauge"):
            raise DecisionError(
                f"{row['locality_id']}: no_suitable_gauge_exists cannot also name a gauge"
            )
        decisions[row["locality_id"]] = Decision(
            locality_id=row["locality_id"],
            decision=row["decision"],
            basis=row["basis"],
            decision_reasoning=row["decision_reasoning"],
            reviewer=row["reviewer"],
            reviewer_qualification=row["reviewer_qualification"],
            reviewed_at=row["reviewed_at"],
            primary_gauge=row.get("primary_gauge") or None,
        )
    return decisions


def gauge_for(decision: Decision, current: str | None) -> str | None:
    """The station this circle should read after the decision is applied."""
    if decision.drops_the_gauge:
        return None
    if decision.decision == "reassign":
        return decision.primary_gauge
    return decision.primary_gauge or current


def problems(
    decisions: dict[str, Decision],
    localities: list[dict[str, Any]],
    stations: dict[str, dict[str, Any]],
) -> list[str]:
    """Everything wrong with this record, in the words needed to fix it.

    Returns all of them rather than the first, because a reviewer working
    through a batch should get one list back, not one error per run.
    """
    known = {row["locality_id"]: row for row in localities}
    found: list[str] = []
    for locality_id, decision in sorted(decisions.items()):
        locality = known.get(locality_id)
        if locality is None:
            found.append(f"{locality_id}: no such circle in the locality registry")
            continue
        if decision.decision == "keep":
            current = locality.get("primary_gauge")
            named = decision.primary_gauge
            if named and named != current:
                found.append(
                    f"{locality_id}: a keep names {named} but the circle reads "
                    f"{current}. Use reassign to change the gauge."
                )
            if not current:
                found.append(
                    f"{locality_id}: a keep needs a gauge to keep, and this circle "
                    "has none"
                )
        if decision.decision == "reassign":
            station = stations.get(decision.primary_gauge or "")
            if station is None:
                found.append(
                    f"{locality_id}: {decision.primary_gauge} is not in the CWC "
                    "station reference"
                )
            elif station.get("station_operational") is False:
                found.append(
                    f"{locality_id}: {decision.primary_gauge} "
                    f"({station.get('site_name') or 'unnamed'}) is not reporting. A "
                    "circle whose right river is gauged by a dead gauge is "
                    "no_suitable_gauge_exists, not a reassign."
                )
    return found


def apply(
    locality: dict[str, Any],
    decision: Decision,
    geometry: dict[str, Any],
) -> dict[str, Any]:
    """The locality record as this decision leaves it.

    `geometry` is the same distance measurement every other mapping carries,
    measured against the gauge the decision settled on. It is recorded, not
    obeyed: the reviewer already saw the distance.
    """
    code = gauge_for(decision, locality.get("primary_gauge"))
    mapping = {
        **geometry,
        "basis": decision.basis,
        "claimed_confidence": None if decision.drops_the_gauge else "high",
        "confidence": NO_GAUGE_CONFIDENCE if decision.drops_the_gauge else "high",
        "method": REVIEWED_METHOD,
        "review": {
            "decision": decision.decision,
            "reasoning": decision.decision_reasoning,
            "reviewed_at": decision.reviewed_at,
            "reviewer": decision.reviewer,
            "reviewer_qualification": decision.reviewer_qualification,
        },
        "reviewed": True,
    }
    return {**locality, "primary_gauge": code, "primary_gauge_mapping": mapping}
