"""Assemble one decision packet per circle in the gauge-topology review queue.

Run with:
  uv run python scripts/build_gauge_decision_packets.py

Workstream 1 of the local-accuracy master plan. Silonijan shipped reading a
gauge 101 km away on a different river, and the distance audit that caught it
can only ever demote — distance is a smoke alarm, not a river model. The fix is
a person deciding, per circle, which river drains it and whether the assigned
gauge sits on that river.

This script does not make that decision and must never be extended to. It
assembles the evidence so the decision costs a reviewer minutes instead of an
afternoon:

- where the circle is, and what it reads today;
- the river under the assigned gauge, from the CWC station reference;
- the named rivers over the circle itself, from the OpenStreetMap snapshot;
- every gauge within a generous radius, with its own river;
- a flag on any candidate whose river also runs over the circle.

That last flag is the one worth being careful about. It is a string comparison
between two independently-maintained name lists, not a hydrological finding. It
says "these two sources use the same word", which is a good place for a reviewer
to look first and nothing more. Candidates are ordered by distance, never by
whether the name matched, so the ordering cannot quietly become a recommendation.

Outputs:
  data/review/gauge-topology/current.json   the packets, decisions left null
  docs/gauge-topology-questions.md          the same packets, for a person

Both are rebuilt from committed inputs, so re-running after a fresh waterway
snapshot or an audit change is safe. Decisions are not stored here — they belong
in a reviewed record that carries who decided and why.
"""

from __future__ import annotations

import argparse
import glob
import importlib.util
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

_spec = importlib.util.spec_from_file_location(
    "_axom_geometry", ROOT / "src" / "axom_flood" / "geometry.py"
)
geometry = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(geometry)

_spec_cwc = importlib.util.spec_from_file_location(
    "_axom_cwc_pipeline", ROOT / "src" / "axom_flood" / "cwc" / "pipeline.py"
)
try:
    cwc_pipeline = importlib.util.module_from_spec(_spec_cwc)
    _spec_cwc.loader.exec_module(cwc_pipeline)
    haversine_km = cwc_pipeline.haversine_km
except Exception:  # pragma: no cover - import shape differs under package install
    from axom_flood.cwc.pipeline import haversine_km  # type: ignore[no-redef]

LOCALITIES = ROOT / "config" / "assam-localities.json"
SHAPES = ROOT / "config" / "assam-circle-shapes.json"
REVIEW = ROOT / "data" / "review" / "locality-gauge-mappings" / "current.json"
STATION_REFERENCE_DIR = ROOT / "data" / "reference" / "cwc"
UPSTREAM_REVIEW = ROOT / "data" / "review" / "upstream-gauge-lags" / "current.json"
WATERWAY_DIR = ROOT / "data" / "reference" / "osm"
OUT_JSON = ROOT / "data" / "review" / "gauge-topology" / "current.json"
OUT_DOC = ROOT / "docs" / "gauge-topology-questions.md"

# Generous on purpose. The point of the packet is to show a reviewer everything
# they might reasonably choose between, including gauges they will reject.
CANDIDATE_RADIUS_KM = 70.0

# The words that differ between the two name lists without changing which river
# is meant. "Nadi" is river in Assamese and Bengali; CWC writes the bare name.
RIVER_NOISE = re.compile(
    r"\b(river|nadi|nadee|nodi|jan|suti|beel)\b|[^a-z0-9 ]", flags=re.IGNORECASE
)


def fold_river(name: str | None) -> str:
    """A comparison key for two river-name spellings, not a canonical name."""
    if not name:
        return ""
    return " ".join(RIVER_NOISE.sub(" ", name.lower()).split())


def river_names_agree(station_river: str | None, circle_rivers: set[str]) -> bool:
    """Do these two name lists use the same word for a river?

    Equality alone is too strict to be useful, and Silonijan is the proof: OSM
    draws the "Dhansiri River" across the circle, CWC files Bokajan's gauge under
    "Dhansiri (South)", and an exact match leaves the one packet this whole
    workstream exists for showing no connection at all.

    So a subset of words counts too — {dhansiri} against {dhansiri, south}. That
    deliberately also matches Dhansiri (North), which is the correct behaviour
    for something whose only job is to say "look here first". It is still a
    comparison of two strings and is labelled as one everywhere it is shown.
    """
    station_key = fold_river(station_river)
    if not station_key:
        return False
    station_words = set(station_key.split())
    for circle_key in circle_rivers:
        if not circle_key:
            continue
        circle_words = set(circle_key.split())
        if station_words <= circle_words or circle_words <= station_words:
            return True
    return False


def latest_station_reference() -> tuple[dict[str, dict[str, Any]], str]:
    """The widest CWC station projection on disk, keyed by station code.

    Widest rather than newest: the roster grew from 37 to 157 when the Base
    station type was admitted, and a packet built from the narrow file would
    silently hide the nearer gauges that whole change existed to surface.
    """
    best: tuple[int, Path, list[dict[str, Any]]] | None = None
    for path in sorted(STATION_REFERENCE_DIR.glob("*.json")):
        stations = json.loads(path.read_text(encoding="utf-8")).get("stations", [])
        rows = stations if isinstance(stations, list) else list(stations.values())
        if best is None or len(rows) > best[0]:
            best = (len(rows), path, rows)
    if best is None:
        raise RuntimeError(
            f"no CWC station reference under {STATION_REFERENCE_DIR} — a packet "
            "without candidate gauges is not a packet"
        )
    _, path, rows = best
    return {row["cwc_station_code"]: row for row in rows}, str(path.relative_to(ROOT))


def latest_waterways() -> tuple[dict[str, Any], str | None]:
    """The most recent OSM waterway snapshot, if one has been taken.

    Absent is a legitimate state, not an error. The packet still answers most of
    itself from the station reference, and the missing section says so out loud
    rather than rendering an empty river list that reads like "no rivers here".
    """
    paths = sorted(glob.glob(str(WATERWAY_DIR / "assam-waterways-*.json")))
    paths = [p for p in paths if not p.endswith(".metadata.json")]
    if not paths:
        return {}, None
    newest = max(paths, key=lambda p: Path(p).stat().st_mtime)
    document = json.loads(Path(newest).read_text(encoding="utf-8"))
    return document.get("circles", {}), str(Path(newest).relative_to(ROOT))


def upstream_questions(
    localities: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], str | None]:
    """Workstream B's candidate pairs, as questions for the same reviewer.

    These ride in the same worksheet on purpose. Both ask the same kind of
    thing — does this water reach that place — and both are answerable from
    river knowledge rather than modelling, so asking them together costs one
    conversation instead of two.

    The lag analysis has already run and gated itself. What it cannot do is
    confirm that two stations sit on the same reach with nothing in between
    that would break the timing. That is the question here, and a pair whose
    numbers failed its own gates is carried through as a non-question rather
    than dropped, so nobody re-derives later why it is missing.
    """
    if not UPSTREAM_REVIEW.exists():
        return [], None
    pointer = json.loads(UPSTREAM_REVIEW.read_text(encoding="utf-8"))
    artifact_path = UPSTREAM_REVIEW.parent / pointer["artifact_path"]
    if not artifact_path.exists():
        return [], None
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))

    reads_downstream: dict[str, list[str]] = {}
    for locality in localities.values():
        code = locality.get("primary_gauge")
        if code:
            reads_downstream.setdefault(code, []).append(locality["name_en"])

    rows: list[dict[str, Any]] = []
    for relationship in artifact["relationships"]:
        quality = relationship["analysis"]["quality"]
        downstream = relationship["downstream"]
        rows.append(
            {
                "circles_reading_downstream": sorted(
                    reads_downstream.get(downstream["cwc_station_code"], [])
                ),
                "decision": None,
                "decision_reasoning": None,
                "downstream": downstream,
                "evidence": {
                    "median_robust_correlation": quality["median_robust_correlation"],
                    "monsoons_measured": quality["eligible_completed_years"],
                    "observed_yearly_lag_range_hours": quality[
                        "observed_yearly_lag_range_hours"
                    ],
                    "passes_quality_gates": quality["passes_quality_gates"],
                    "recommended_lag_hours": quality["recommended_lag_hours"],
                    "stable_year_fraction": quality["stable_year_fraction"],
                },
                "relationship_id": relationship["relationship_id"],
                "reviewed_at": None,
                "reviewer": None,
                "topology_basis": relationship["topology"]["basis"],
                "upstream": relationship["upstream"],
            }
        )
    rows.sort(
        key=lambda row: (
            not row["evidence"]["passes_quality_gates"],
            -row["evidence"]["median_robust_correlation"],
        )
    )
    return rows, str(artifact_path.relative_to(ROOT))


def line_length_km(line: list[list[float]]) -> float:
    return sum(
        haversine_km(line[index], line[index + 1]) for index in range(len(line) - 1)
    )


def rivers_over_circle(
    entry: dict[str, Any], rings: list[list[list[float]]] | None
) -> tuple[list[dict[str, Any]], str]:
    """Named rivers near the circle, longest run first.

    With an outline, "over the circle" means the vertices that fall inside it.
    Those outlines are drawing grade — most have not passed the boundary review —
    so this is used only to rank names for a reader, never to compute a value.
    Without an outline the box around the circle is all we have, and the method
    string says which of the two produced the list.
    """
    rivers = entry.get("rivers") or {}
    if not rivers:
        return [], "no_snapshot"
    scored: list[dict[str, Any]] = []
    if rings:
        for name, lines in rivers.items():
            inside_km = 0.0
            for line in lines:
                run = [point for point in line if geometry.point_in_rings(point, rings)]
                if len(run) > 1:
                    inside_km += line_length_km(run)
            if inside_km > 0:
                scored.append({"river": name, "length_inside_km": round(inside_km, 1)})
        if scored:
            scored.sort(key=lambda item: -item["length_inside_km"])
            return scored, "vertices_inside_circle_outline"
        # Rivers were downloaded but none has a vertex inside the outline. That
        # is itself worth showing — it usually means the outline is wrong.
        method = "nearby_only_none_inside_outline"
    else:
        method = "bounding_box_only_no_outline"
    for name, lines in rivers.items():
        scored.append(
            {"river": name, "length_nearby_km": round(sum(map(line_length_km, lines)), 1)}
        )
    scored.sort(key=lambda item: -item["length_nearby_km"])
    return scored[:12], method


def candidates(
    centroid: list[float],
    assigned_code: str | None,
    stations: dict[str, dict[str, Any]],
    circle_river_keys: set[str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for code, station in stations.items():
        point = station.get("coordinates")
        if not point:
            continue
        distance = haversine_km(centroid, point)
        if distance > CANDIDATE_RADIUS_KM:
            continue
        river = station.get("river")
        rows.append(
            {
                "cwc_station_code": code,
                "distance_km": round(distance, 1),
                "is_assigned": code == assigned_code,
                "is_upstream_of_assam": station.get("is_upstream_of_assam"),
                "river": river,
                "river_name_also_over_circle": river_names_agree(river, circle_river_keys),
                "site_name": station.get("site_name"),
                "station_operational": station.get("station_operational"),
                "station_type": station.get("station_type"),
            }
        )
    rows.sort(key=lambda row: row["distance_km"])
    return rows


def build_packets() -> dict[str, Any]:
    localities = {
        item["locality_id"]: item
        for item in json.loads(LOCALITIES.read_text(encoding="utf-8"))["localities"]
    }
    review = json.loads(REVIEW.read_text(encoding="utf-8"))
    stations, station_ref = latest_station_reference()
    waterways, waterway_ref = latest_waterways()
    outlines = geometry.load_circle_outlines(SHAPES)
    upstream, upstream_ref = upstream_questions(localities)

    packets: list[dict[str, Any]] = []
    for record in review["records"]:
        if not (record.get("far") or record.get("much_nearer_gauge_exists")):
            continue
        locality_id = record["locality_id"]
        locality = localities[locality_id]
        rings = outlines.get(locality_id)
        rivers, river_method = rivers_over_circle(waterways.get(locality_id, {}), rings)
        river_keys = {fold_river(item["river"]) for item in rivers}
        assigned_code = locality.get("primary_gauge")
        assigned = stations.get(assigned_code) if assigned_code else None
        nearby = candidates(locality["centroid"], assigned_code, stations, river_keys)
        assigned_river_over_circle = (
            river_names_agree(assigned.get("river"), river_keys) if assigned else False
        )
        packets.append(
            {
                "assigned_gauge": {
                    "cwc_station_code": assigned_code,
                    "distance_km": record.get("distance_km"),
                    "mapping_basis": (locality.get("primary_gauge_mapping") or {}).get(
                        "basis"
                    ),
                    "river": assigned.get("river") if assigned else None,
                    "river_name_also_over_circle": assigned_river_over_circle,
                    "site_name": assigned.get("site_name") if assigned else None,
                    "station_operational": assigned.get("station_operational")
                    if assigned
                    else None,
                },
                "candidate_gauges_operational": sum(
                    1 for row in nearby if row["station_operational"]
                ),
                "candidate_gauges": nearby,
                "centroid": locality["centroid"],
                "claimed_confidence": record.get("confidence"),
                "decision": None,
                "decision_reasoning": None,
                "district": locality["district"],
                "flagged_far": bool(record.get("far")),
                "flagged_much_nearer_exists": bool(record.get("much_nearer_gauge_exists")),
                "has_circle_outline": bool(rings),
                "locality_id": locality_id,
                "priority": "high"
                if record.get("far") and record.get("much_nearer_gauge_exists")
                else "normal",
                "review_reason": record.get("review_reason"),
                "reviewed_at": None,
                "reviewer": None,
                "reviewer_qualification": None,
                "revenue_circle": locality["name_en"],
                "rivers_over_circle": rivers,
                "rivers_over_circle_method": river_method,
            }
        )

    packets.sort(
        key=lambda packet: (
            packet["priority"] != "high",
            -(packet["assigned_gauge"]["distance_km"] or 0),
        )
    )
    return {
        "attribution": "River names © OpenStreetMap contributors, ODbL",
        "candidate_radius_km": CANDIDATE_RADIUS_KM,
        "decisions": {
            "allowed": ["keep", "reassign", "no_suitable_gauge_exists"],
            "note": (
                "no_suitable_gauge_exists is a first-class outcome. A circle with "
                "no gauge on its own drainage should say so rather than borrow a "
                "number from the wrong river."
            ),
        },
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "packets": packets,
        "provenance": {
            "built_by": "scripts/build_gauge_decision_packets.py",
            "circle_outlines": "config/assam-circle-shapes.json",
            "flagged_from": str(REVIEW.relative_to(ROOT)),
            "localities": str(LOCALITIES.relative_to(ROOT)),
            "station_reference": station_ref,
            "upstream_lag_artifact": upstream_ref,
            "waterway_snapshot": waterway_ref,
        },
        "queue": "gauge_topology_review",
        "schema_version": 2,
        "upstream_pairs": upstream,
        "totals": {
            "high_priority": sum(1 for p in packets if p["priority"] == "high"),
            "no_reporting_gauge_within_radius": sum(
                1 for p in packets if p["candidate_gauges_operational"] == 0
            ),
            "packets": len(packets),
            "reads_a_stopped_gauge": sum(
                1 for p in packets if p["assigned_gauge"]["station_operational"] is False
            ),
            "upstream_pairs_asked": sum(
                1 for row in upstream if row["evidence"]["passes_quality_gates"]
            ),
            "upstream_pairs_withheld": sum(
                1 for row in upstream if not row["evidence"]["passes_quality_gates"]
            ),
            "with_river_names": sum(1 for p in packets if p["rivers_over_circle"]),
            "without_circle_outline": sum(1 for p in packets if not p["has_circle_outline"]),
        },
    }


def render_packet(packet: dict[str, Any]) -> list[str]:
    assigned = packet["assigned_gauge"]
    lines = [
        f"### {packet['revenue_circle']} — {packet['district']}",
        "",
        f"**Reads now:** {assigned['site_name'] or '—'} "
        f"(`{assigned['cwc_station_code'] or '—'}`) on the "
        f"**{assigned['river'] or 'unrecorded'}**, {assigned['distance_km']} km away"
        + ("." if assigned["station_operational"] else " — **and not reporting.**"),
    ]
    if assigned["mapping_basis"]:
        lines.append(f"Recorded reason for that mapping: *{assigned['mapping_basis']}*.")
    lines.append("")

    if packet["rivers_over_circle"]:
        if packet["rivers_over_circle_method"] == "vertices_inside_circle_outline":
            lines.append("**Rivers running through this circle**, longest first:")
        elif packet["rivers_over_circle_method"] == "bounding_box_only_no_outline":
            lines.append(
                "**Named rivers near this circle** — no outline is drawn for it, "
                "so this is everything in the surrounding box, not what crosses it:"
            )
        else:
            lines.append(
                "**Named rivers nearby.** None has a point inside the drawn "
                "outline, which usually means the outline is wrong rather than "
                "that the circle has no river:"
            )
        lines.append("")
        for item in packet["rivers_over_circle"][:8]:
            length = item.get("length_inside_km", item.get("length_nearby_km"))
            lines.append(f"- {item['river']} ({length} km)")
    else:
        lines.append(
            "**Rivers running through this circle:** not available — no waterway "
            "snapshot covers it. Answer from your own knowledge of the ground."
        )
    lines.append("")

    def table(rows: list[dict[str, Any]]) -> list[str]:
        out = ["| Gauge | River | Distance | Notes |", "| --- | --- | --- | --- |"]
        for row in rows:
            notes = []
            if row["is_assigned"]:
                notes.append("**reads this now**")
            if row["river_name_also_over_circle"]:
                notes.append("river name matches one over the circle")
            if row["is_upstream_of_assam"]:
                notes.append("upstream of Assam")
            out.append(
                f"| {row['site_name']} (`{row['cwc_station_code']}`) "
                f"| {row['river'] or '—'} | {row['distance_km']} km "
                f"| {', '.join(notes) or ''} |"
            )
        return out

    live = [row for row in packet["candidate_gauges"] if row["station_operational"]]
    dead = [row for row in packet["candidate_gauges"] if not row["station_operational"]]

    lines.append("**Gauges within 70 km that are reporting:**")
    lines.append("")
    if live:
        lines.extend(table(live[:10]))
    else:
        lines.append("**None.** Every gauge within 70 km of this circle is switched off.")
    lines.append("")

    if dead:
        # A reviewer who reassigns a circle to a dead gauge has spent a decision
        # for nothing, and CWC has more stations off than on. But hiding them
        # would also hide the useful answer "the right river is gauged, and that
        # gauge is dead" — which is what no_suitable_gauge_exists is for.
        lines.append(
            f"<details><summary>{len(dead)} more nearby, but not reporting</summary>"
        )
        lines.append("")
        lines.extend(table(dead[:10]))
        lines.append("")
        lines.append("</details>")
        lines.append("")
    lines.append(
        "**Question:** does the "
        f"{assigned['river'] or 'assigned'} reach this circle's water? "
        "Keep it, name a better gauge, or say no gauge fits."
    )
    lines.append("")
    return lines


def render_upstream(rows: list[dict[str, Any]]) -> list[str]:
    """The second half of the worksheet: does a rise here arrive there?"""
    asked = [row for row in rows if row["evidence"]["passes_quality_gates"]]
    withheld = [row for row in rows if not row["evidence"]["passes_quality_gates"]]

    lines = [
        "---",
        "",
        "# Part 2 — does a rise upstream reach here?",
        "",
        "A different question, same kind of knowledge. If a gauge upstream rises",
        "and that water reliably arrives downstream some hours later, the site can",
        "warn people before their own river moves.",
        "",
        "We measured the timing against seven monsoons of readings. What the",
        "measurement **cannot** tell us is whether the two gauges are really on the",
        "same stretch of water, or whether something between them — a tributary",
        "joining, a barrage, a big bend — breaks the link. That is the question.",
        "",
        "⚠️ Matching timing is not proof. Two gauges can rise together because the",
        "same rain fell on both, with no water travelling between them at all.",
        "That is exactly the mistake this review exists to catch.",
        "",
        f"**{len(asked)} pairs to check.**",
        "",
    ]
    for row in asked:
        up = row["upstream"]
        down = row["downstream"]
        evidence = row["evidence"]
        low, high = evidence["observed_yearly_lag_range_hours"]
        lines.extend(
            [
                f"### {up['site_name']} → {down['site_name']}",
                "",
                f"**Upstream:** {up['site_name']} on the {up['river']}, "
                f"{up.get('district')}, {up.get('state')}.",
                f"**Downstream:** {down['site_name']} on the {down['river']}, "
                f"{down.get('district')}, {down.get('state')}.",
                "",
                f"**What the readings show:** a rise upstream has usually shown up "
                f"downstream about **{evidence['recommended_lag_hours']:.0f} hours** "
                f"later. Across {evidence['monsoons_measured']} monsoons that gap ran "
                f"from {low} to {high} hours.",
            ]
        )
        if row["circles_reading_downstream"]:
            circles = ", ".join(row["circles_reading_downstream"][:6])
            more = len(row["circles_reading_downstream"]) - 6
            lines.append(
                f"**Who this would help:** {circles}"
                + (f", and {more} more" if more > 0 else "")
                + " — these read the downstream gauge."
            )
        else:
            lines.append(
                "**Who this would help:** no revenue circle currently reads the "
                "downstream gauge, so this pair adds lead time only if a circle is "
                "reassigned to it in Part 1."
            )
        lines.extend(
            [
                "",
                "**Question:** is the water at "
                f"{up['site_name']} the same water that reaches "
                f"{down['site_name']}? Anything major in between?",
                "",
            ]
        )

    if withheld:
        lines.extend(
            [
                "## Not asking about these",
                "",
                "The timing here was too weak or too unstable to be worth your time.",
                "Listed so nobody wonders later why they are missing.",
                "",
            ]
        )
        for row in withheld:
            up = row["upstream"]
            down = row["downstream"]
            low, high = row["evidence"]["observed_yearly_lag_range_hours"]
            lines.append(
                f"- **{up['site_name']} → {down['site_name']}** "
                f"({up['river']}): the gap ranged from {low} to {high} hours between "
                "years, which is too loose to build a sentence on."
            )
        lines.append("")
    return lines


def render_doc(document: dict[str, Any]) -> str:
    totals = document["totals"]
    lines = [
        "# River questions for someone who knows Assam's rivers",
        "",
        "Everything needed to answer is on the page, so nothing here should send",
        "you looking something up.",
        "",
        "Two parts:",
        "",
        f"- **Part 1** — {totals['packets']} places that may be reading the wrong",
        "  river. The bigger job.",
        f"- **Part 2** — {totals['upstream_pairs_asked']} pairs of gauges, where a rise",
        "  at one may give warning time to the other. Quick.",
        "",
        f"Built {document['generated_at'][:10]} by",
        "`scripts/build_gauge_decision_packets.py` from",
        f"`{document['provenance']['flagged_from']}`.",
        "",
        "## What is being asked",
        "",
        "Every circle below shows a river level taken from a gauge. The distance",
        "audit flagged these because the gauge is far away, or because a much",
        "closer one exists. Distance alone proves nothing — a far gauge on the",
        "**same river** can be right, and a close one on a **different river** is",
        "useless. That is the judgement no script can make.",
        "",
        "Three answers are allowed:",
        "",
        "- **Keep** — the gauge is on the water that reaches this circle.",
        "- **Reassign** — name the gauge that is.",
        "- **No gauge fits** — nothing on this circle's drainage is gauged. This is",
        "  a real answer, not a failure. Better to say so than to quietly show a",
        "  number from the wrong river.",
        "",
        "⚠️ Where a table says *river name matches one over the circle*, that is a",
        "string comparison between two name lists. It means the two sources used",
        "the same word. It is a place to look first, not an answer.",
        "",
        "River names come from OpenStreetMap (© OpenStreetMap contributors, ODbL).",
        "",
        f"**{totals['packets']} circles.** {totals['high_priority']} are in the first",
        "group: those are both far from their gauge *and* have a much closer one.",
        "",
        "---",
        "",
        "# Part 1 — is this place reading the right river?",
        "",
        "## First: far gauge, and a much closer one exists",
        "",
    ]
    seen_normal = False
    for packet in document["packets"]:
        if packet["priority"] != "high" and not seen_normal:
            seen_normal = True
            lines.extend(
                [
                    "---",
                    "",
                    "## Then: the rest of the flagged circles",
                    "",
                    "Same question, lower urgency.",
                    "",
                ]
            )
        lines.extend(render_packet(packet))
    if document["upstream_pairs"]:
        lines.extend(render_upstream(document["upstream_pairs"]))
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json-only", action="store_true")
    args = parser.parse_args()

    document = build_packets()
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {OUT_JSON.relative_to(ROOT)}")
    if not args.json_only:
        OUT_DOC.write_text(render_doc(document), encoding="utf-8")
        print(f"wrote {OUT_DOC.relative_to(ROOT)}")

    totals = document["totals"]
    print(
        f"{totals['packets']} packets "
        f"({totals['high_priority']} high priority); "
        f"{totals['with_river_names']} have river names; "
        f"{totals['without_circle_outline']} have no circle outline"
    )
    if document["provenance"]["waterway_snapshot"] is None:
        print("no waterway snapshot found — run scripts/fetch_osm_waterways.py first")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
