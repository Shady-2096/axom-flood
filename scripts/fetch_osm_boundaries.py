"""Snapshot Assam's OpenStreetMap administrative boundaries from Overpass.

Run with:
  uv run python scripts/fetch_osm_boundaries.py

Why this is a script and not a documented curl
----------------------------------------------
The first boundary download was taken by hand on 2026-07-27 and its metadata
file points at `scripts/build_osm_places.py` for the query, which is the
consumer rather than the fetcher. That was fine while the outlines were only
ever drawn. Workstream 0 promotes them to something computed against, so the
retrieval itself has to be reproducible: the query, the moment it ran, the
relation identifiers it returned, and the checksum of the bytes.

Snapshots are content-addressed and never overwritten. An older download stays
on disk so a boundary score can be re-run against the exact geometry that
produced it.

Level 6 is the revenue circle in Assam's OSM tagging and level 5 is the
district. Both are pulled: the district relations are what let a circle be
matched to the right district rather than to whichever same-named circle in
another district happened to be seen first.

OpenStreetMap data is ODbL. Anything published from these artifacts has to
carry the "© OpenStreetMap contributors" credit.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = ROOT / "data" / "reference" / "osm"

ENDPOINT = "https://overpass-api.de/api/interpreter"

# `out geom` returns every way member's full coordinate list. That is the whole
# point here — the stored snapshot must be unsimplified, because simplification
# is a display decision made downstream and has to stay reversible.
QUERY = (
    "[out:json][timeout:300];"
    'area["ISO3166-2"="IN-AS"]->.a;'
    'relation(area.a)["boundary"="administrative"]["admin_level"~"^(5|6)$"];'
    "out geom;"
)

ATTRIBUTION = "© OpenStreetMap contributors, ODbL"


def fetch(endpoint: str, query: str, timeout: float) -> bytes:
    response = httpx.post(
        endpoint,
        content=query.encode(),
        headers={
            "Content-Type": "text/plain; charset=utf-8",
            # Overpass asks callers to identify themselves so it can throttle a
            # misbehaving client rather than the shared IP it sits behind.
            "User-Agent": "axom-flood/1.0 (+https://github.com/Shady-2096/Axom-floods)",
        },
        timeout=timeout,
    )
    response.raise_for_status()
    return response.content


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--endpoint", default=ENDPOINT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--timeout", type=float, default=300.0)
    args = parser.parse_args()

    payload = fetch(args.endpoint, QUERY, args.timeout)
    digest = hashlib.sha256(payload).hexdigest()

    document = json.loads(payload)
    elements = document.get("elements", [])
    if not elements:
        raise SystemExit("Overpass returned no elements; refusing to write a snapshot")

    levels = Counter(element.get("tags", {}).get("admin_level") for element in elements)
    if levels.get("6", 0) < 150:
        # Assam has roughly 180 revenue circles. A short answer means the query
        # was truncated or the area lookup failed, and writing it would quietly
        # shrink the map.
        raise SystemExit(
            f"only {levels.get('6', 0)} admin_level=6 relations returned; expected ~180"
        )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    data_path = args.output_dir / f"assam-boundaries-{digest}.json"
    meta_path = args.output_dir / f"assam-boundaries-{digest}.metadata.json"
    if data_path.exists():
        print(f"unchanged since the last snapshot: {data_path.name}")
        return

    data_path.write_bytes(payload)
    meta_path.write_text(
        json.dumps(
            {
                "source": "OpenStreetMap via Overpass API",
                "endpoint": args.endpoint,
                "licence": "ODbL 1.0",
                "attribution": ATTRIBUTION,
                "retrieved_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "sha256": digest,
                "query": QUERY,
                "content": "Assam admin_level 5 and 6 boundary relations, unsimplified geometry",
                "element_count": len(elements),
                "admin_level_counts": {
                    level: count for level, count in sorted(levels.items(), key=str)
                },
                "relation_ids": sorted(
                    element["id"] for element in elements if element.get("type") == "relation"
                ),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )

    size_mib = data_path.stat().st_size / 1024 / 1024
    print(f"wrote {data_path.name} ({size_mib:.1f} MiB)")
    print(f"elements {len(elements)}  " + "  ".join(
        f"level {level}: {count}" for level, count in sorted(levels.items(), key=str)
    ))


if __name__ == "__main__":
    main()
