"""Keep every revenue circle's centroid inside the circle it belongs to.

`build_localities.py` derives a centroid as the median position of the UDISE
village points whose names matched the circle. Where that name match picked up
villages from the wrong part of the state, the median lands outside the circle
entirely. Gohpur's sat 100 km west of Gohpur, in the Tezpur area, and the map
drew its gauge line from there; Helem and Biswanath were 66 km and 46 km out.
40 of 190 circles were affected.

The centroid is not decoration. It is where the map draws the line from, and it
is what the gauge-distance audit measures, so a wrong one both misdraws the map
and mismeasures the review queue that decides which gauge a circle should read.

This script replaces a centroid only when it falls outside its own circle's
outline and the outline gives a defensible interior point. A centroid that is
already inside its circle is left exactly as it is, including the ones that sit
away from the town of the same name — a circle is an area, and its centre is
allowed not to be its namesake village.

Using the outlines this way widens what they are for. Their provenance note in
`config/assam-circle-shapes.json` says they are for drawing and "are not used to
place anyone", and that still holds: this places a circle's own centre for
drawing and for distance review. It never places a person, a camp, or a gauge,
and it never chooses which gauge a circle reads.

Two modes, matching scripts/audit_gauge_mappings.py:

  --check   Report centroids that are outside their circle and exit non-zero.
  --write   Correct them in place.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from axom_flood.cwc.pipeline import haversine_km
from axom_flood.geometry import (
    CORRECTED_METHOD,
    corrected_centre,
    load_circle_outlines,
    point_in_rings,
    representative_point,
)

ROOT = Path(__file__).resolve().parents[1]
LOCALITIES = ROOT / "config" / "assam-localities.json"
SHAPES = ROOT / "config" / "assam-circle-shapes.json"

__all__ = ["corrected_centre", "find_corrections", "main"]


def find_corrections(
    localities: list[dict[str, Any]],
    shapes: dict[str, list[list[list[float]]]],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Centroids sitting outside their own circle, and those we cannot fix."""
    corrections: list[dict[str, Any]] = []
    unfixable: list[str] = []
    for locality in localities:
        locality_id = locality["locality_id"]
        rings = shapes.get(locality_id)
        centroid = locality.get("centroid")
        if not rings or not centroid:
            continue
        if point_in_rings(centroid, rings):
            continue
        replacement = representative_point(rings)
        if replacement is None:
            unfixable.append(locality_id)
            continue
        corrections.append(
            {
                "locality_id": locality_id,
                "was": centroid,
                "now": replacement,
                "moved_km": round(haversine_km(centroid, replacement), 1),
                "was_method": locality.get("centroid_method"),
            }
        )
    corrections.sort(key=lambda item: -item["moved_km"])
    return corrections, unfixable


def apply_corrections(
    localities: list[dict[str, Any]], corrections: list[dict[str, Any]]
) -> None:
    by_id = {locality["locality_id"]: locality for locality in localities}
    for correction in corrections:
        locality = by_id[correction["locality_id"]]
        locality["centroid"] = correction["now"]
        locality["centroid_method"] = CORRECTED_METHOD


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    parser.add_argument("--localities", type=Path, default=LOCALITIES)
    parser.add_argument("--shapes", type=Path, default=SHAPES)
    args = parser.parse_args(argv)

    document = json.loads(args.localities.read_text())
    localities = document["localities"]
    shapes = load_circle_outlines(args.shapes)
    corrections, unfixable = find_corrections(localities, shapes)

    if unfixable:
        print(f"No interior point could be derived for {len(unfixable)} circles:")
        for locality_id in unfixable:
            print(f"  {locality_id}")

    if not corrections:
        print(f"All {len(shapes)} circles with an outline hold a centroid inside it.")
        return 1 if unfixable else 0

    if args.check:
        print(f"{len(corrections)} centroids fall outside their own circle:")
        for correction in corrections:
            print(
                f"  {correction['locality_id']:<34} "
                f"{correction['moved_km']:>6.1f} km from where it should be"
            )
        print("\nRun scripts/audit_locality_centroids.py --write to correct them.")
        return 1

    apply_corrections(localities, corrections)
    args.localities.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n")
    print(f"Corrected {len(corrections)} centroids.")
    for correction in corrections[:10]:
        print(f"  {correction['locality_id']:<34} moved {correction['moved_km']:>6.1f} km")
    return 1 if unfixable else 0


if __name__ == "__main__":
    raise SystemExit(main())
