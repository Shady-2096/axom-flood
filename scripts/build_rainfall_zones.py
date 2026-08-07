"""Build the grid-cell weight table that turns rainfall grids into circle numbers.

Run with:
  uv run python scripts/build_rainfall_zones.py            # write the artifact
  uv run python scripts/build_rainfall_zones.py --check    # verify, change nothing

Workstream C of the local-accuracy master plan, first half.

This carries no rainfall. It is pure geometry: for each revenue circle whose
boundary passed Workstream 0, which grid cells overlap it and by how much. That
makes it the one part of the rainfall work that needs no NASA Earthdata account,
no credentials, and no network — and it is the part everything else waits on,
because a downloaded IMERG grid is not a circle number until something says how
the cells divide up.

It is also reusable beyond rainfall. Any lat/lon raster on the same grid — a
terrain band, a flood extent share — aggregates through the same weights.

The artifact is content-addressed and never overwritten in place, matching how
gauge and boundary artifacts are handled. A rebuild that changes nothing rewrites
the same digest; a rebuild that changes something leaves the old one readable.

Which one is current is written down
------------------------------------
Content-addressed files need something mutable to say which is live, and this
one has to be a file rather than a filesystem detail. The reader used to take the
newest modification time, which is right on a working copy and wrong everywhere
else: a fresh `git clone` stamps every file with the checkout time, so the
"newest" becomes whichever hash sorts first. Measured on a clean clone of this
repository, that picked the 82-circle table over the 101-circle one — no error,
no warning, just nineteen circles quietly missing from a scheduled publish.

So the pointer is `current.json`, the same shape the published rainfall and
gauge artifacts already use.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from axom_flood.rainfall.zonal import (  # noqa: E402
    IMERG_CELL_DEGREES,
    ZONAL_FORBIDS,
    ZONAL_PERMITS,
    cell_weights,
    load_measured_boundaries,
)

REVIEW = ROOT / "data" / "review" / "circle-boundaries" / "current.json"
OUT_DIR = ROOT / "data" / "processed" / "rainfall-zones"
POINTER = OUT_DIR / "current.json"


def build(cell_degrees: float) -> dict[str, Any]:
    review = json.loads(REVIEW.read_text())
    geojson_path = ROOT / review["passed_geojson"]
    boundaries = load_measured_boundaries(geojson_path, REVIEW)

    zones = []
    for boundary in sorted(boundaries, key=lambda item: item.locality_id):
        weights = cell_weights(boundary, cell_degrees=cell_degrees)
        zones.append({**weights.as_dict(), "boundary": boundary.as_dict()})

    every_cell = sorted({cell for zone in zones for cell in
                         (entry["grid_cell_id"] for entry in zone["cells"])})
    return {
        "schema_version": 1,
        "record": "rainfall_zone_weights",
        "cell_degrees": cell_degrees,
        "grid": (
            "lat/lon cells named by their south-west corner; IMERG V07 native "
            "resolution when cell_degrees is 0.1"
        ),
        "aggregation": "area_weighted; no centre-point assignment",
        "area_method": (
            "spherical, by the boundary integral -∮sin(φ)dλ; exactly additive, "
            "so the clipped pieces of a circle sum to the whole circle"
        ),
        "permits": ZONAL_PERMITS,
        "forbids": ZONAL_FORBIDS,
        "attribution": review.get("attribution"),
        "provenance": {
            "boundary_review": str(REVIEW.relative_to(ROOT)),
            "boundary_geojson": review["passed_geojson"],
            "boundary_sha256": review["provenance"]["boundary_sha256"],
            "built_by": "scripts/build_rainfall_zones.py",
            "note": (
                "Circles absent from this file have no analysis-grade boundary "
                "and must be skipped explicitly rather than estimated."
            ),
        },
        "totals": {
            "circles": len(zones),
            "distinct_cells": len(every_cell),
            "circles_in_one_cell": sum(1 for zone in zones if zone["cell_count"] == 1),
            "largest_cell_count": max((zone["cell_count"] for zone in zones), default=0),
        },
        "zones": zones,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--cell-degrees", type=float, default=IMERG_CELL_DEGREES)
    args = parser.parse_args()

    document = build(args.cell_degrees)
    totals = document["totals"]

    # Digest the content without the build stamp, so an unchanged rebuild is a
    # no-op rather than a new file every time somebody runs the script.
    body = json.dumps(document, indent=2, sort_keys=True).encode()
    digest = sha256(body).hexdigest()
    target = OUT_DIR / f"{digest}.json"

    print(
        f"{totals['circles']} circles over {totals['distinct_cells']} cells; "
        f"{totals['circles_in_one_cell']} fit inside a single cell, "
        f"largest spans {totals['largest_cell_count']}"
    )

    pointed_at = (
        json.loads(POINTER.read_text()).get("revision_id") if POINTER.exists() else None
    )

    if args.check:
        state = "present" if target.exists() else "NOT WRITTEN"
        print(f"would write {target.relative_to(ROOT)} ({state})")
        if pointed_at != digest:
            print(
                f"current.json points at {pointed_at or 'nothing'}, not {digest}",
                file=sys.stderr,
            )
            return 1
        return 0 if target.exists() else 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        document["generated_at"] = datetime.now(UTC).isoformat()
        target.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
    # Rewritten every run, including when the digest did not change. It is the
    # only mutable file here and the only thing that says which table is live.
    POINTER.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "record": "rainfall_zone_weights_pointer",
                "revision_id": digest,
                "zones_url": f"data/processed/rainfall-zones/{digest}.json",
                "generated_at": datetime.now(UTC).isoformat(),
                "totals": totals,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    print(f"wrote {target.relative_to(ROOT)}")
    print(f"pointer {POINTER.relative_to(ROOT)} -> {digest[:12]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
