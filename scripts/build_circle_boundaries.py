"""Build analysis-grade revenue-circle boundaries and score every one of them.

Run with:
  uv run python scripts/build_circle_boundaries.py \
    --boundaries data/reference/osm/assam-boundaries-<sha>.json

This is Workstream 0, Track 2 of the master plan. Until a circle has a polygon
somebody has measured, five other workstreams stall at their last step: zonal
rainfall, HAND membership, model-reach mapping, satellite overlap, and placing a
citizen report without asking the person.

Two outputs, deliberately separate:

  data/processed/circle-boundaries/<sha>.geojson
      Full-resolution outlines for circles that passed. Content-addressed and
      never overwritten, so a score can always be re-read against the exact
      geometry that produced it.

  data/review/circle-boundaries/current.json
      The quality record for *every* circle, passed or failed: how it was
      matched, how many independent points it was tested against, what share of
      them landed inside, how far the ones that did not landed, whether it
      overlaps a neighbour, and what it is therefore allowed to be used for.

A point is counted as agreeing if it falls inside the outline or within 500 m of
it. `quality.py` carries the argument; the short version is that the grade being
granted is averaging over a few hundred square kilometres, the coarsest consumer
is rainfall on cells about 11 km across, and a school 300 m over a shared border
says nothing about either. Every record publishes the strict containment share
next to the tolerant one, so the tolerance is checkable rather than trusted.

Promotion is per circle, never in bulk, and the bar is recorded in the artifact
rather than assumed by the reader. A circle that fails stays null and every
downstream workstream must skip it explicitly.

What a passing grade permits
----------------------------
`zonal` means the outline is good enough to average something over the circle —
rainfall, a terrain band, a share of low ground. It does **not** mean the outline
can tell one person whether their house is inside a flood extent. Nothing in this
repository may promote a circle from `zonal` to individual placement without a
separate review, because the error that matters for one household is invisible in
an agreement rate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from axom_flood.boundaries.osm import (
    DISTRICT_SUCCESSION,
    assign_districts,
    load_relations,
    match_localities,
)
from axom_flood.boundaries.quality import (
    CELL_DEGREES,
    MAX_FOREIGN_SHARE,
    MIN_POINTS_FOR_A_SCORE,
    MIN_POINTS_TO_BE_SWALLOWED,
    TOLERANCE_KM,
    cell_area_sq_km,
    cell_of,
    measure_contamination,
    measure_topology,
    school_points_by_locality,
    score_circle,
    village_counts,
)

ROOT = Path(__file__).resolve().parents[1]

DEFAULT_UDISE = ROOT / "data" / "reference" / "udise"
LOCALITIES = ROOT / "config" / "assam-localities.json"
VILLAGE_INDEX = ROOT / "config" / "assam-village-search-index.json"
BOUNDARY_DIR = ROOT / "data" / "processed" / "circle-boundaries"
REVIEW_DIR = ROOT / "data" / "review" / "circle-boundaries"

ATTRIBUTION = "© OpenStreetMap contributors, ODbL"

# The bar a circle has to clear to be computed against. 0.90 is chosen, not
# derived: nine of every ten schools a circle claims fall inside the outline
# drawn for it. It is defensible for averaging a value over an area and is
# nowhere near good enough to place an individual, which is why the grade it
# grants is named `zonal` and not `placement`.
PASS_AGREEMENT = 0.90

# Two neighbouring circles digitised from slightly different traces of the same
# river will share a thin strip along it. That is a drafting artefact, not two
# circles claiming the same ground, so a small shared area is tolerated. Anything
# above this is a duplicate relation or a wrong match and disqualifies the circle.
MAX_OVERLAP_SHARE = 0.02

def latest_snapshot(directory: Path, prefix: str, suffix: str = ".json") -> Path:
    candidates = sorted(
        (path for path in directory.glob(f"{prefix}*{suffix}") if ".metadata" not in path.name),
        key=lambda path: path.stat().st_mtime,
    )
    if not candidates:
        raise SystemExit(f"no {prefix}*{suffix} snapshot under {directory}")
    return candidates[-1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--boundaries", type=Path, default=None)
    parser.add_argument("--udise-csv", type=Path, default=None)
    parser.add_argument("--pass-agreement", type=float, default=PASS_AGREEMENT)
    parser.add_argument("--max-overlap", type=float, default=MAX_OVERLAP_SHARE)
    parser.add_argument("--max-foreign-share", type=float, default=MAX_FOREIGN_SHARE)
    parser.add_argument(
        "--write-refs",
        action="store_true",
        help="populate boundary_geojson_ref in config/assam-localities.json for passing circles",
    )
    args = parser.parse_args()

    boundaries_path = args.boundaries or latest_snapshot(
        ROOT / "data" / "reference" / "osm", "assam-boundaries-"
    )
    udise_csv = args.udise_csv or latest_snapshot(DEFAULT_UDISE, "assam-schools-", ".csv")

    payload = boundaries_path.read_bytes()
    boundaries_hash = hashlib.sha256(payload).hexdigest()
    elements = json.loads(payload)["elements"]

    localities = json.loads(LOCALITIES.read_text())["localities"]
    village_index = json.loads(VILLAGE_INDEX.read_text())["villages"]

    districts, circles = load_relations(elements)
    assign_districts(circles, districts)
    match = match_localities(localities, circles)

    points = school_points_by_locality(village_index, udise_csv)
    villages = village_counts(village_index)

    outlines = {
        locality_id: relation.rings for locality_id, relation in match.matched.items()
    }
    cells, shared_cells = measure_topology(outlines)
    # The other half of the question agreement cannot ask: how much of what sits
    # inside each outline belongs to a different circle.
    contamination = measure_contamination(cells, points)
    # Which circle owns each grid cell, so a point that fell outside its own
    # circle can be told where it did land. A stray point that landed in the
    # neighbouring circle means the outline and the village-to-circle join
    # disagree about a border; one that landed in another district means the
    # village name matched a school somewhere else entirely. Those are different
    # problems with different fixes, and an agreement rate alone hides both.
    cell_owner: dict[tuple[int, int], str] = {}
    for locality_id, filled in cells.items():
        for cell in filled:
            cell_owner.setdefault(cell, locality_id)
    areas = {
        locality_id: sum(cell_area_sq_km(row) for _, row in filled)
        for locality_id, filled in cells.items()
    }
    overlap_pairs = {
        tuple(sorted((left, right)))
        for left, partners in shared_cells.items()
        for right in partners
    }

    records: list[dict[str, Any]] = []
    passed: dict[str, Any] = {}
    by_id = {locality["locality_id"]: locality for locality in localities}

    for locality in localities:
        locality_id = locality["locality_id"]
        base = {
            "locality_id": locality_id,
            "revenue_circle": locality["revenue_circle"],
            "district": locality["district"],
        }
        relation = match.matched.get(locality_id)
        if relation is None:
            reason = next(
                (item for item in match.unresolved if item["locality_id"] == locality_id), None
            )
            records.append({
                **base,
                "matched": False,
                "grade": "none",
                "blocked_by": reason["reason"] if reason else "unmatched",
                "detail": reason["detail"] if reason else "",
                "resolvable_by_matching": (
                    reason.get("resolvable_by_matching", True) if reason else True
                ),
                "candidates": reason["candidates"] if reason else [],
            })
            continue

        dirt = contamination[locality_id]
        own_points = points.get(locality_id, [])
        score = score_circle(
            locality_id, relation.rings, own_points, villages.get(locality_id, 0)
        )
        own_cells = cells.get(locality_id) or set()
        strays: dict[str, int] = {}
        for longitude, latitude in own_points:
            cell = cell_of(longitude, latitude)
            if cell in own_cells:
                continue
            owner = cell_owner.get(cell)
            strays[owner or "no_circle"] = strays.get(owner or "no_circle", 0) + 1
        stray_district = sum(
            count for owner, count in strays.items()
            if owner != "no_circle" and by_id.get(owner, {}).get("district") == locality["district"]
        )
        conflicts = {
            other: len(own_cells & (cells.get(other) or set()))
            for other in shared_cells.get(locality_id, {})
        }
        shared_area = sum(
            cell_area_sq_km(row)
            for other in conflicts
            for _, row in own_cells & (cells.get(other) or set())
        )
        area = areas.get(locality_id, 0.0)
        overlap_share = shared_area / area if area else 0.0

        # One OSM relation standing in for both Census halves of a split circle.
        # The outline is the whole circle, so it cannot describe either half, and
        # scoring it against one half's points is meaningless in both directions.
        twins = sorted(
            other for other, twin in match.matched.items()
            if other != locality_id and twin is relation
        )
        # OpenStreetMap draws the whole circle and does not model the Census
        # split at all. Confirmed 2026-07-31 against district records: the split
        # is real — Baksa and Nalbari each hold a portion of Ghograpar, Dhubri
        # and Kokrajhar each hold a portion of Bilasipara — so this is an OSM
        # coverage gap, not a Census error, and no matching rule resolves it.
        if twins:
            grade, blocked = "none", "one_relation_serves_two_census_halves"
        elif not score.has_enough_points:
            grade, blocked = "none", "too_few_independent_points"
        elif overlap_share > args.max_overlap:
            grade, blocked = "none", "overlaps_another_circle"
        elif (score.agreement or 0) < args.pass_agreement:
            grade, blocked = "none", "agreement_below_threshold"
        elif (dirt.foreign_share or 0) > args.max_foreign_share:
            # Checked after agreement, because a circle failing both should be
            # reported against the simpler test. This one catches the opposite
            # error: an outline large enough to score well on its own points
            # while standing over a neighbour's ground.
            grade, blocked = "none", "outline_holds_other_circles_points"
        elif dirt.swallowed:
            # And the case a share cannot reach: a large outline with plenty of
            # its own points can hold every point a small circle has while still
            # sitting well under the share bar. The small circle then has nowhere
            # left to be, which is the same error the share test exists for.
            grade, blocked = "none", "outline_holds_every_point_of_another_circle"
        else:
            grade, blocked = "zonal", None

        # Where the disagreement points. Assam has created revenue circles since
        # 2011, and the village-to-circle column this point set is joined through
        # is Census 2011. A circle whose stray points nearly all landed in a
        # neighbour inside its own district looks exactly like a circle that has
        # since been split: the outline is current, the village list is not.
        # That is a different problem from points landing in another district,
        # which means a village name matched a school somewhere else entirely.
        # Neither is proof, and both keep the circle out of the analysis set —
        # but they lead to different repairs, so the record says which.
        outside = score.points - score.within_tolerance
        failure_mode = None
        if grade != "zonal" and outside:
            if stray_district >= outside * 0.8:
                failure_mode = "strays_land_in_a_neighbour_in_the_same_district"
            elif stray_district <= outside * 0.2:
                failure_mode = "strays_land_outside_this_district"
            else:
                failure_mode = "strays_land_in_both"

        record = {
            **base,
            "matched": True,
            "osm_id": f"relation/{relation.osm_id}",
            "osm_name": relation.name,
            "osm_district": relation.district,
            "osm_district_share": round(relation.district_share, 4),
            "independent_points": score.points,
            "points_inside": score.inside,
            "points_within_tolerance": score.within_tolerance,
            # `agreement` is the tolerant share and is what promotion uses.
            # `agreement_strict` is plain containment, published beside it so the
            # tolerance never has to be taken on trust.
            "agreement": None if score.agreement is None else round(score.agreement, 4),
            "agreement_strict": (
                None if score.agreement_strict is None else round(score.agreement_strict, 4)
            ),
            "tolerance_m": round(TOLERANCE_KM * 1000),
            # How far the real disagreements are. A median under about 2 km is
            # two records differing about where a shared border runs; beyond
            # 10 km the outline covers different ground or the school join is
            # wrong, and those need different repairs.
            "median_stray_km": (
                None if score.median_stray_km is None else round(score.median_stray_km, 2)
            ),
            "max_stray_km": (
                None if score.max_stray_km is None else round(score.max_stray_km, 2)
            ),
            # What this outline holds that is not its own. Agreement can only go
            # up as an outline grows, so this is the only number that can see an
            # outline standing over a neighbour.
            "own_points_held": dirt.own_inside,
            "foreign_points_held": dirt.foreign_inside,
            "foreign_share": (
                None if dirt.foreign_share is None else round(dirt.foreign_share, 4)
            ),
            "foreign_points_from": dict(dirt.worst_sources),
            # Circles this outline holds entirely, which no share can show.
            "swallowed_circles": dict(dirt.swallowed),
            "villages_with_independent_centre": score.villages,
            "area_sq_km": round(area, 2),
            "overlap_area_sq_km": round(shared_area, 2),
            "overlap_share": round(overlap_share, 4),
            "overlaps": sorted(other for other, count in conflicts.items() if count),
            "stray_points_by_circle": dict(
                sorted(strays.items(), key=lambda item: -item[1])[:5]
            ),
            "stray_points_in_own_district": stray_district,
            "shares_relation_with": twins,
            "resolvable_by_matching": not twins,
            "grade": grade,
        }
        if blocked:
            record["blocked_by"] = blocked
        if failure_mode:
            record["failure_mode"] = failure_mode
        records.append(record)
        if grade == "zonal":
            passed[locality_id] = relation

    feature_collection = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": locality_id,
                "properties": {
                    "locality_id": locality_id,
                    "revenue_circle": by_id[locality_id]["revenue_circle"],
                    "district": by_id[locality_id]["district"],
                    "osm_id": f"relation/{relation.osm_id}",
                    "grade": "zonal",
                },
                "geometry": {
                    "type": "Polygon" if len(relation.rings) == 1 else "MultiPolygon",
                    "coordinates": (
                        [[[round(x, 6), round(y, 6)] for x, y in relation.rings[0]]]
                        if len(relation.rings) == 1
                        else [
                            [[[round(x, 6), round(y, 6)] for x, y in ring]]
                            for ring in relation.rings
                        ]
                    ),
                },
            }
            for locality_id, relation in sorted(passed.items())
        ],
    }
    geojson_bytes = (
        json.dumps(feature_collection, ensure_ascii=False, sort_keys=True) + "\n"
    ).encode()
    geojson_hash = hashlib.sha256(geojson_bytes).hexdigest()

    BOUNDARY_DIR.mkdir(parents=True, exist_ok=True)
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    geojson_path = BOUNDARY_DIR / f"{geojson_hash}.geojson"
    if not geojson_path.exists():
        geojson_path.write_bytes(geojson_bytes)

    graded = [record for record in records if record["grade"] == "zonal"]
    scored = [
        record for record in records
        if record.get("agreement") is not None
        and record.get("independent_points", 0) >= MIN_POINTS_FOR_A_SCORE
    ]
    review = {
        "schema_version": 1,
        "queue": "circle_boundary_quality",
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "attribution": ATTRIBUTION,
        "provenance": {
            "boundary_source": "OpenStreetMap via Overpass API, admin_level=6",
            "boundary_snapshot": boundaries_path.name,
            "boundary_sha256": boundaries_hash,
            "point_source": (
                "UDISE school coordinates joined to Census villages by name and district"
            ),
            "point_source_path": str(udise_csv.relative_to(ROOT)),
            "simplification": "none — outlines are stored at full OSM resolution",
            "district_succession": DISTRICT_SUCCESSION,
        },
        "rules": {
            "pass_agreement": args.pass_agreement,
            "min_independent_points": MIN_POINTS_FOR_A_SCORE,
            "max_overlap_share": args.max_overlap,
            "topology_cell_degrees": CELL_DEGREES,
            "max_foreign_share": args.max_foreign_share,
            "min_points_to_be_swallowed": MIN_POINTS_TO_BE_SWALLOWED,
            "min_points_to_be_swallowed_reason": (
                "a share has a denominator, so a large outline with many of its own "
                "points can hold a small circle whole without the share reaching a "
                "third. An outline holding every point another circle has leaves that "
                "circle nowhere to be, whatever fraction of this one it amounts to"
            ),
            "max_foreign_share_reason": (
                "agreement can only rise as an outline grows, so it cannot see an "
                "outline standing over a neighbour's ground. Among circles that "
                "otherwise look sound the fringe of neighbours' points near a shared "
                "border reaches about a quarter; past a third the outline is "
                "describing somebody else's land and an average over it would be "
                "attributed to the wrong circle"
            ),
            "agreement_tolerance_m": round(TOLERANCE_KM * 1000),
            "agreement_tolerance_reason": (
                "a point this far outside the outline is not a disagreement at the "
                "resolution this grade is for: the coarsest consumer is rainfall on a "
                "0.1-degree grid, whose cells are about 11 km across. Both the tolerant "
                "and the strict share are published per circle"
            ),
            "grade_zonal_permits": (
                "averaging a value over the whole circle — rainfall, a terrain band, a share "
                "of low ground"
            ),
            "grade_zonal_forbids": (
                "deciding whether an individual point, household, or report lies inside the "
                "circle; that needs a separate review this score cannot stand in for"
            ),
        },
        "totals": {
            "localities": len(localities),
            "matched_to_a_relation": len(match.matched),
            "scored": len(scored),
            "passed": len(graded),
            "overlapping_pairs": len(overlap_pairs),
            "unresolved": len(match.unresolved),
        },
        "passed_geojson": f"data/processed/circle-boundaries/{geojson_hash}.geojson",
        "records": sorted(records, key=lambda record: record["locality_id"]),
    }
    (REVIEW_DIR / "current.json").write_text(
        json.dumps(review, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )

    if args.write_refs:
        document = json.loads(LOCALITIES.read_text())
        ref = f"data/processed/circle-boundaries/{geojson_hash}.geojson#{{locality_id}}"
        for locality in document["localities"]:
            locality["boundary_geojson_ref"] = (
                ref.format(locality_id=locality["locality_id"])
                if locality["locality_id"] in passed
                else None
            )
        LOCALITIES.write_text(
            json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        )

    print(f"matched      {len(match.matched)} of {len(localities)} localities")
    print(f"scored       {len(scored)} (at least {MIN_POINTS_FOR_A_SCORE} independent points)")
    print(
        f"passed       {len(graded)} at >= {args.pass_agreement:.0%} agreement "
        f"(points within {TOLERANCE_KM * 1000:.0f} m of the outline count as inside)"
    )
    print(f"overlaps     {len(overlap_pairs)} pairs")
    print(f"unresolved   {len(match.unresolved)}")
    print(f"boundaries   {geojson_path.relative_to(ROOT)} "
          f"({geojson_path.stat().st_size / 1024 / 1024:.1f} MiB)")
    print(f"review       {(REVIEW_DIR / 'current.json').relative_to(ROOT)}")
    blocked: dict[str, int] = {}
    for record in records:
        if record.get("blocked_by"):
            blocked[record["blocked_by"]] = blocked.get(record["blocked_by"], 0) + 1
    for reason, count in sorted(blocked.items(), key=lambda item: -item[1]):
        print(f"  blocked: {reason:38s} {count}")


if __name__ == "__main__":
    main()
