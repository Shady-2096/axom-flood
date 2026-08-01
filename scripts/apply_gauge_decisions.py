"""Turn reviewed gauge-topology answers into the mappings the site reads from.

Run with:
  uv run python scripts/apply_gauge_decisions.py --check
  uv run python scripts/apply_gauge_decisions.py --write

Workstream 1 of the local-accuracy master plan, second half.
`scripts/build_gauge_decision_packets.py` builds the questions; a person answers
them in `config/gauge-topology-decisions.json`; this applies the answers.

  --check   Validate every decision and print what each one does, changing
            nothing. Run this before committing an answer sheet.

  --write   Apply them to config/assam-localities.json and the review queue.

Two properties worth keeping
----------------------------

**One writer.** The write path is `scripts/audit_gauge_mappings.py`, imported
rather than reimplemented. Two scripts writing the same fields is how a mapping
ends up meaning one thing on Tuesday and another on Wednesday.

**Nothing here decides anything.** This script refuses bad decisions; it never
makes one, never picks a gauge, and never fills in a reviewer. A decision with
no name against it is not a decision.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent

_spec = importlib.util.spec_from_file_location(
    "audit_gauge_mappings", ROOT / "scripts" / "audit_gauge_mappings.py"
)
audit = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(audit)

from axom_flood.gauges import decisions as gauge_decisions  # noqa: E402


def describe(
    decision: gauge_decisions.Decision,
    locality: dict[str, Any],
    stations: dict[str, dict[str, Any]],
) -> str:
    """One line saying what this decision does to this circle."""
    where = f"{locality['revenue_circle']} — {locality['district']}"
    current = locality.get("primary_gauge")
    if decision.drops_the_gauge:
        return (
            f"{where}: drops {current or 'its gauge'} and shows no river reading. "
            f"Reviewed by {decision.reviewer} ({decision.reviewer_qualification})."
        )
    code = gauge_decisions.gauge_for(decision, current)
    station = stations.get(code or "") or {}
    name = station.get("site_name") or code
    river = station.get("river")
    on = f" on the {river}" if river else ""
    verb = "keeps" if decision.decision == "keep" else f"moves from {current} to"
    return (
        f"{where}: {verb} {name} ({code}){on}. "
        f"Reviewed by {decision.reviewer} ({decision.reviewer_qualification})."
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    parser.add_argument("--decisions", type=Path, default=audit.DECISIONS)
    args = parser.parse_args()

    stations = audit.bl.load_station_reference(args.data_dir)
    if not stations:
        print(f"no CWC station reference under {args.data_dir}/reference/cwc", file=sys.stderr)
        return 2

    try:
        reviewed = gauge_decisions.load(args.decisions)
    except gauge_decisions.DecisionError as error:
        print(f"{args.decisions.name}: {error}", file=sys.stderr)
        return 2

    document = json.loads(audit.LOCALITIES.read_text())
    localities = document["localities"]
    faults = gauge_decisions.problems(reviewed, localities, stations)
    if faults:
        print("These decisions cannot be applied:", file=sys.stderr)
        for fault in faults:
            print(f"  {fault}", file=sys.stderr)
        return 1

    if not reviewed:
        print(
            f"No decisions recorded yet in {args.decisions.relative_to(ROOT)}. "
            "The questions are in docs/gauge-topology-questions.md."
        )
        return 0

    known = {row["locality_id"]: row for row in localities}
    counts = {name: 0 for name in gauge_decisions.ALLOWED_DECISIONS}
    for locality_id, decision in sorted(reviewed.items()):
        counts[decision.decision] += 1
        print(f"  {describe(decision, known[locality_id], stations)}")
    print(
        f"{len(reviewed)} decided: {counts['keep']} kept, "
        f"{counts['reassign']} reassigned, "
        f"{counts['no_suitable_gauge_exists']} with no gauge that fits."
    )

    if args.check:
        return 0
    # One writer. The audit re-measures every circle and rewrites the queue, and
    # honours these decisions on the way through.
    return audit.main(
        ["--write", "--data-dir", str(args.data_dir), "--decisions", str(args.decisions)]
    )


if __name__ == "__main__":
    raise SystemExit(main())
