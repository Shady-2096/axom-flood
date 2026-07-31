"""Snapshot the named rivers around each circle in the gauge-topology queue.

Run with:
  uv run python scripts/fetch_osm_waterways.py

Why this exists
---------------
Workstream 1 asks a reviewer one question per circle: which river drains this
place, and is the gauge we read sitting on it? The first half of that question
is answerable from a map, and answering it for the reviewer is the difference
between a packet they can decide from and a packet that sends them to look
something up.

The station reference already names the river under every gauge. What was
missing was the river *over the circle*. This fills that in from OpenStreetMap.

Scope is deliberately narrow: named `waterway=river` ways inside a box around
each flagged circle. Streams are excluded — Assam has tens of thousands and
none of them carry a CWC gauge, so they would bury the two or three names that
actually decide the question.

One box per circle rather than one query for Assam. The flagged circles run
from Baksa to Dhemaji, so their union is most of the state, and a state-wide
`out geom` for rivers is a large payload to re-download every time one circle
is re-examined.

Snapshots are content-addressed and never overwritten, matching
`fetch_osm_boundaries.py`. A packet built last week can be re-read against the
exact geometry that produced it.

OpenStreetMap data is ODbL. Anything published from these artifacts has to
carry the "© OpenStreetMap contributors" credit.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = ROOT / "data" / "reference" / "osm"
LOCALITIES = ROOT / "config" / "assam-localities.json"
SHAPES = ROOT / "config" / "assam-circle-shapes.json"
REVIEW = ROOT / "data" / "review" / "locality-gauge-mappings" / "current.json"

ENDPOINT = "https://overpass-api.de/api/interpreter"

# The Overpass `area[...]` lookup for Assam resolves slowly enough that the
# public instance returns a dispatcher timeout before the query starts. A plain
# bounding box costs nothing to resolve, and every box here is well inside
# Assam, so the area filter was only ever belt-and-braces.
QUERY_TEMPLATE = (
    "[out:json][timeout:{timeout}];"
    'way["waterway"="river"]["name"]({south},{west},{north},{east});'
    "out geom;"
)

# Half-degree of latitude is about 55 km. A circle's own outline is the better
# box when we have one; this is the fallback for the circles whose outline OSM
# does not draw, and it is generous on purpose — a river that drains a circle
# can be named on a segment just outside it.
FALLBACK_HALF_SPAN_DEG = 0.25
BOX_PAD_DEG = 0.05


def flagged_locality_ids(review_path: Path) -> list[str]:
    """The circles the distance audit put in front of a reviewer.

    Read from the committed queue rather than recomputed here. The audit owns
    that judgement, and a second implementation of it would be a second thing
    to keep in step.
    """
    review = json.loads(review_path.read_text(encoding="utf-8"))
    return [
        record["locality_id"]
        for record in review["records"]
        if record.get("far") or record.get("much_nearer_gauge_exists")
    ]


def outline_boxes(shapes_path: Path) -> dict[str, tuple[float, float, float, float]]:
    """Bounding box per locality, from the drawn circle outlines.

    These outlines are not analysis grade — most have not passed the boundary
    review — but a bounding box is far coarser than the geometry itself, so an
    outline too rough to place a household in is still fine for deciding which
    rivers to download.
    """
    shapes = json.loads(shapes_path.read_text(encoding="utf-8"))
    boxes: dict[str, tuple[float, float, float, float]] = {}
    for circle in shapes["circles"]:
        lons: list[float] = []
        lats: list[float] = []
        for ring in circle["rings"]:
            for lon, lat in ring:
                lons.append(lon)
                lats.append(lat)
        if not lons:
            continue
        box = (min(lats), min(lons), max(lats), max(lons))
        for locality_id in circle["locality_ids"]:
            boxes[locality_id] = box
    return boxes


def box_for(
    locality: dict[str, Any],
    boxes: dict[str, tuple[float, float, float, float]],
) -> tuple[tuple[float, float, float, float], str]:
    box = boxes.get(locality["locality_id"])
    if box:
        source = "circle_outline_bbox"
    else:
        lon, lat = locality["centroid"]
        box = (
            lat - FALLBACK_HALF_SPAN_DEG,
            lon - FALLBACK_HALF_SPAN_DEG,
            lat + FALLBACK_HALF_SPAN_DEG,
            lon + FALLBACK_HALF_SPAN_DEG,
        )
        source = "centroid_square"
    south, west, north, east = box
    padded = (
        round(south - BOX_PAD_DEG, 6),
        round(west - BOX_PAD_DEG, 6),
        round(north + BOX_PAD_DEG, 6),
        round(east + BOX_PAD_DEG, 6),
    )
    return padded, source


def fetch(
    client: httpx.Client,
    box: tuple[float, float, float, float],
    timeout: int,
    attempts: int,
) -> tuple[list[dict[str, Any]], str]:
    """One box, retried on the public instance's load-shedding.

    Overpass sheds load in two shapes: a 504, and an HTML error page served
    under HTTP 200. The second is the dangerous one — parsed loosely it looks
    like a circle with no rivers, which is exactly the wrong thing to write
    into a reviewer's packet. Both are treated as retryable failures, and a
    run that exhausts its attempts stops rather than storing a gap.
    """
    south, west, north, east = box
    query = QUERY_TEMPLATE.format(
        timeout=timeout, south=south, west=west, north=north, east=east
    )
    last: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            response = client.post(ENDPOINT, data={"data": query}, timeout=timeout + 30)
            response.raise_for_status()
            if not response.text.lstrip().startswith("{"):
                raise RuntimeError(
                    f"Overpass returned a non-JSON body: {response.text[:200]}"
                )
            return response.json().get("elements", []), query
        except (httpx.HTTPError, RuntimeError) as error:
            last = error
            if attempt < attempts:
                backoff = 10 * attempt
                print(f"    Overpass busy ({type(error).__name__}); retrying in {backoff}s")
                time.sleep(backoff)
    raise RuntimeError(f"Overpass failed after {attempts} attempts: {last}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument(
        "--pause",
        type=float,
        default=4.0,
        help="seconds between queries; the public Overpass instance is shared",
    )
    parser.add_argument("--max-attempts", type=int, default=4)
    args = parser.parse_args()

    localities = {
        item["locality_id"]: item
        for item in json.loads(LOCALITIES.read_text(encoding="utf-8"))["localities"]
    }
    boxes = outline_boxes(SHAPES)
    targets = flagged_locality_ids(REVIEW)

    circles: dict[str, Any] = {}
    started = datetime.now(UTC)
    with httpx.Client(headers={"User-Agent": "axom-flood/waterways (assamflood.org)"}) as client:
        for index, locality_id in enumerate(targets, start=1):
            locality = localities[locality_id]
            box, box_source = box_for(locality, boxes)
            elements, query = fetch(client, box, args.timeout, args.max_attempts)
            rivers: dict[str, list[list[list[float]]]] = {}
            for element in elements:
                name = element["tags"]["name"]
                line = [[point["lon"], point["lat"]] for point in element.get("geometry", [])]
                if line:
                    rivers.setdefault(name, []).append(line)
            circles[locality_id] = {
                "bbox_south_west_north_east": list(box),
                "bbox_source": box_source,
                "query": query,
                "river_names": sorted(rivers),
                "rivers": rivers,
                "way_count": len(elements),
            }
            print(
                f"[{index}/{len(targets)}] {locality['name_en']}: "
                f"{len(rivers)} named rivers across {len(elements)} ways"
            )
            if index < len(targets):
                time.sleep(args.pause)

    payload = {
        "attribution": "© OpenStreetMap contributors, ODbL",
        "circles": circles,
        "endpoint": ENDPOINT,
        "query_template": QUERY_TEMPLATE,
        "schema_version": 1,
        "scope": "named waterway=river ways around each gauge-topology review circle",
        "source": "OpenStreetMap via Overpass API",
    }
    body = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
    digest = hashlib.sha256(body).hexdigest()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    out = args.output_dir / f"assam-waterways-{digest}.json"
    out.write_bytes(body)
    meta = {
        "circle_count": len(circles),
        "fetch_started_at": started.isoformat().replace("+00:00", "Z"),
        "fetch_finished_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "fetched_by": "scripts/fetch_osm_waterways.py",
        "licence": "ODbL — © OpenStreetMap contributors",
        "sha256": digest,
        "unique_river_names": sorted(
            {name for circle in circles.values() for name in circle["river_names"]}
        ),
    }
    (args.output_dir / f"assam-waterways-{digest}.metadata.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"\nwrote {out.relative_to(ROOT)}")
    print(f"{len(meta['unique_river_names'])} distinct river names across {len(circles)} circles")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
