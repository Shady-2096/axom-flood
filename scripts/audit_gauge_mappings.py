"""Re-apply the gauge-distance audit to the committed locality registry.

`build_localities.py` runs the audit as part of a full rebuild, but that needs the
30 MB Census workbook, which is not in the repository. This script applies the
same audit — importing the same functions, never a second copy of them — to
`config/assam-localities.json` and the review queue that goes with it.

Two modes:

  --check   Compare the committed artifacts against what the audit says they
            should contain, print the differences, and exit non-zero. This is the
            CI guard. It answers one question: has anyone changed a gauge mapping
            without the distance being re-checked?

  --write   Update the artifacts in place.

Why this exists at all: Silonijan shipped reading from a gauge 101 km away in
another basin, presented with the same confidence as a reviewed match, and no
step in the build objected. Distance is not hydrology and this script does not
pretend otherwise — it never picks a gauge and never promotes a mapping. It only
refuses to let an unexamined mapping keep calling itself checked.
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
    "build_localities", ROOT / "scripts" / "build_localities.py"
)
bl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bl)

LOCALITIES = ROOT / "config" / "assam-localities.json"
REVIEW = ROOT / "data" / "review" / "locality-gauge-mappings" / "current.json"


def claimed_confidence(locality: dict[str, Any]) -> str:
    """What the mapping table claims for this circle, before any audit.

    Read from the table, never from the artifact. The artifact is exactly where
    the clobbered values live: sixteen circles in the post-2011 districts were
    written out as "high" because a district-reassignment tuple overwrote the
    gauge confidence, so trusting the committed file would launder the bug this
    script exists to undo.

    The override table is keyed on the Census spelling of the circle, which is not
    always the canonical name, so every alias is tried and the answer is accepted
    only when the gauge code it produces matches the one on the record.
    """
    supplement = next(
        (
            item
            for item in bl.CURRENT_ADMIN_LOCALITIES
            if item["locality_id"] == locality["locality_id"]
        ),
        None,
    )
    if supplement:
        return supplement["gauge_confidence"]

    district = locality.get("census_2011_district") or locality["district"]
    code = locality.get("primary_gauge")
    for name in [locality["revenue_circle"], *(locality.get("source_aliases") or [])]:
        candidate_code, _, confidence = bl.mapping_for(district, name)
        if (candidate_code or None) == code:
            return confidence or "unverified"
    # No key reproduces this record's gauge, so the table has moved on from the
    # artifact. Refusing to guess is the honest answer, and unverified is the
    # answer that cannot overstate.
    return "unverified"


def audited(
    localities: list[dict[str, Any]],
    stations: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """The registry and review queue as the audit says they should be."""
    updated: list[dict[str, Any]] = []
    queue: list[dict[str, Any]] = []
    for locality in localities:
        mapping = dict(locality.get("primary_gauge_mapping") or {})
        centroid = locality.get("centroid")
        code = locality.get("primary_gauge")
        if not centroid:
            updated.append(locality)
            continue
        geometry = bl.gauge_geometry(centroid, code, stations)
        claimed = claimed_confidence(locality)
        confidence = (
            "unverified"
            if geometry["far"] or geometry["much_nearer_gauge_exists"]
            else claimed
        )
        mapping.update(
            {
                "claimed_confidence": claimed,
                "confidence": confidence,
                "reviewed": confidence == "high",
                **geometry,
            }
        )
        updated.append({**locality, "primary_gauge_mapping": mapping})
        if confidence != "high":
            queue.append(
                {
                    "locality_id": locality["locality_id"],
                    "district": locality.get("census_2011_district")
                    or locality["district"],
                    "revenue_circle": locality["revenue_circle"],
                    "proposed_primary_gauge": code,
                    "confidence": confidence,
                    **geometry,
                    "basis": mapping.get("basis"),
                    "review_reason": bl.review_reason(geometry, claimed),
                }
            )
    # Worst first. A queue sorted by district is a queue nobody starts.
    queue.sort(key=lambda row: -(row["distance_km"] or 0))
    return updated, queue


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    args = parser.parse_args()

    stations = bl.load_station_reference(args.data_dir)
    if not stations:
        print(f"no CWC station reference under {args.data_dir}/reference/cwc", file=sys.stderr)
        return 2

    document = json.loads(LOCALITIES.read_text())
    localities, queue = audited(document["localities"], stations)

    if args.write:
        document["localities"] = localities
        document["provenance"]["gauge_distance_audit"] = (
            f"Distance to the assigned gauge is measured against the recorded CWC "
            f"station reference. Beyond {bl.FAR_KM:.0f} km, or more than "
            f"{bl.MUCH_NEARER_KM:.0f} km further than the nearest station, a mapping "
            "is forced to unverified and queued for hydrology review whatever the "
            "mapping table claimed. It never promotes a mapping or picks a gauge."
        )
        LOCALITIES.write_text(
            json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        )
        REVIEW.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "queue": "primary_gauge_mapping",
                    "records": queue,
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
        far = [row for row in queue if row["far"] or row["much_nearer_gauge_exists"]]
        print(
            f"{len(localities)} circles audited, {len(queue)} queued, "
            f"{len(far)} flagged by distance"
        )
        return 0

    committed = {item["locality_id"]: item for item in document["localities"]}
    drift = [
        item["locality_id"]
        for item in localities
        if committed[item["locality_id"]].get("primary_gauge_mapping")
        != item["primary_gauge_mapping"]
    ]
    if drift:
        print(
            "Gauge mappings are stale — run scripts/audit_gauge_mappings.py --write",
            file=sys.stderr,
        )
        for locality_id in drift[:20]:
            print(f"  {locality_id}", file=sys.stderr)
        if len(drift) > 20:
            print(f"  … and {len(drift) - 20} more", file=sys.stderr)
        return 1
    print(f"{len(localities)} gauge mappings audited, all current")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
