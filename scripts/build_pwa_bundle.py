"""Publish content-hashed Phase 1 PWA data artifacts and a mutable pointer."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from axom_flood.alerts.sentence import generate_sentence

IST = ZoneInfo("Asia/Kolkata")

# How long a gauge may be silent before it stops being drawn on the map.
#
# CWC publishes its retired stations alongside its live ones, and it retires them
# in batches: 44 Assam-region gauges last reported on 2025-04-29 or 2025-04-30,
# and five more froze on 2022-10-12. Those five are duplicate codes for stations
# that are still live under a different divisional code, so they put a second,
# permanently blank pin beside a working gauge.
#
# Drawn on the map they are 59 pins that will never carry a reading, and the map
# has no way to say "this one is never coming back" as against "this one has not
# reported this hour", which is the state that actually matters during a flood.
#
# A year is deliberately far longer than any real outage. Nothing is deleted:
# the ingest still fetches them, the snapshot still records them, and the moment
# one reports again it crosses back over this line on its own.
PUBLISH_SILENT_AFTER_DAYS = 365


def read(path: Path) -> Any:
    return json.loads(path.read_text())


def pointed_at(directory: str) -> Path:
    """The artifact `current.json` in `directory` names.

    This replaced a newest-modification-time pick, which is right only while the
    run that wrote the file is the run reading it. Every Cloud Run job starts
    from a fresh `git clone`, and `git checkout` stamps every file at once, so
    "newest" collapses to whichever hash the filesystem hands back first --
    silently, out of 122 river snapshots and 7 camp lists.

    A missing or dangling pointer is fatal. The alternative is guessing, and a
    bundle built from the wrong artifact looks entirely normal in the output --
    which is exactly what let the same bug in the rainfall zone table survive
    until someone measured it on a clean clone.
    """

    pointer = Path(directory) / "current.json"
    if not pointer.exists():
        raise RuntimeError(f"no {pointer}; rebuild the artifact to write one")
    revision = json.loads(pointer.read_text())["revision_id"]
    target = Path(directory) / f"{revision}.json"
    if not target.exists():
        raise RuntimeError(f"{pointer} names {revision}, which is not on disk")
    return target


def write_immutable(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() != payload:
        raise RuntimeError(f"refusing to overwrite immutable artifact: {path}")
    if not path.exists():
        path.write_bytes(payload)


def _retired_from_service(gauge: dict[str, Any], *, now: datetime) -> bool:
    """Whether a gauge has been silent long enough to stop drawing it.

    A gauge that has never reported at all is kept. Absence of history is not
    evidence of retirement — it may be newly added — and the map already has an
    honest state for it.
    """
    observed_at = gauge.get("observed_at")
    if not observed_at:
        return False
    silent_for = now - datetime.fromisoformat(observed_at)
    return silent_for.days > PUBLISH_SILENT_AFTER_DAYS


def main() -> None:
    now = datetime.now(IST)
    cwc = read(pointed_at("data/processed/cwc"))
    localities = read(Path("config/assam-localities.json"))
    villages_path = Path("config/assam-village-search-index.json")
    villages_bytes = villages_path.read_bytes()
    village_hash = hashlib.sha256(villages_bytes).hexdigest()
    # Town and locality names the Census has no unit for -- Gaurisagar and the
    # like. Small enough to ride in the main bundle, which matters: these are the
    # names people actually type, and they should not sit behind the 9.5 MB
    # village index download.
    #
    # Only what a search result needs travels: the name, the matching key, and
    # the locality it resolves to. Coordinates, OSM ids and the circle and
    # district names are all recoverable from the locality or are not used at
    # all, and carrying them doubled the bundle every reader pays for on a first
    # visit. The full records stay in config/assam-osm-places.json.
    osm_places_path = Path("config/assam-osm-places.json")
    osm_places = []
    if osm_places_path.exists():
        for place in read(osm_places_path)["places"]:
            entry = {
                "n": place["place_name"],
                "k": place["normalized_name"],
                "l": place["locality_ids"],
            }
            if place.get("name_as"):
                entry["a"] = place["name_as"]
            osm_places.append(entry)

    shapes_path = Path("config/assam-circle-shapes.json")
    # By the pointer, not by mtime. Only the daily job re-runs the UDISE matcher,
    # so on the two-hourly CWC run this directory is seven committed artifacts
    # with identical checkout times and nothing to separate them.
    camps_document = read(pointed_at("data/processed/camp-matches"))
    camps = [
        camp
        for camp in camps_document.get("camps", [])
        if camp.get("geocode_confidence") in {"high", "source_coordinates"}
        or camp.get("udise_match_confidence") == "high"
    ]
    # When these listings were taken off the district notifications, which is a
    # different question from when this bundle was built and a very different one
    # from when a gauge last reported.
    #
    # The camps screen had no date of its own, so it printed the river gauge's
    # reading age instead: "3.2 hours old" over a list read from documents saved
    # eighteen days earlier. Every word of it true about the gauge and none of it
    # true about the camps. A camp list is the one thing here somebody might act
    # on by getting in a boat.
    #
    # This is our fetch time, not the district's publication time -- the
    # notifications are PDFs and most carry no date we can parse. So it is
    # published as "saved", which is exactly what it is, and never as "published"
    # or "updated".
    camps_saved_at = None
    source_artifact = camps_document.get("camp_source_artifact")
    if source_artifact:
        source_path = Path("data/processed/district-camps") / f"{source_artifact}.json"
        if source_path.exists():
            camps_saved_at = read(source_path).get("generated_at")
    gauges = []
    retired = 0
    for gauge in cwc["stations"]:
        if _retired_from_service(gauge, now=now):
            retired += 1
            continue
        item = dict(gauge)
        item["sentence_en"] = generate_sentence(item, now=now)["text"]
        gauges.append(item)
    print(f"Publishing {len(gauges)} gauges; {retired} silent for over a year withheld.")

    # Phase 2 crowd-report aggregate. The lazy-loaded report screen reads
    # only the reconciled, anonymised open dataset -- never an individual
    # report. If no crowd run has published an artifact yet the field is null
    # and the screen shows a placeholder rather than a single-report view.
    crowd_url = None
    try:
        crowd_paths = sorted(Path("data/processed/crowd").glob("*.json"))
        if crowd_paths:
            crowd_bytes = crowd_paths[-1].read_bytes()
            crowd_hash = hashlib.sha256(crowd_bytes).hexdigest()
            crowd_name = f"crowd-{crowd_hash}.json"
            write_immutable(Path("pwa/data") / crowd_name, crowd_bytes)
            crowd_url = f"data/{crowd_name}"
    except FileNotFoundError:
        pass

    # ASDMA impact is a separate, lazy artifact. Only its URL and minimal
    # publication metadata enter the main bundle, so a daily administrative
    # report never delays the primary CWC river bulletin.
    impact_pointer_path = Path("static/data/impact-current.json")
    impact_pointer_url = None
    if impact_pointer_path.exists():
        impact_pointer_url = "data/impact-current.json"

    # The map outlines are only fetched when someone opens the picker, so they
    # never delay a river reading.
    circle_shapes_url = None
    if shapes_path.exists():
        shapes_bytes = (
            json.dumps(read(shapes_path), ensure_ascii=False, separators=(",", ":"),
                       sort_keys=True) + "\n"
        ).encode()
        shapes_name = f"shapes-{hashlib.sha256(shapes_bytes).hexdigest()}.json"
        write_immutable(Path("pwa/data") / shapes_name, shapes_bytes)
        circle_shapes_url = f"data/{shapes_name}"

    bundle = {
        "schema_version": 1,
        "circle_shapes_url": circle_shapes_url,
        "osm_places": osm_places,
        "osm_attribution": "© OpenStreetMap contributors, ODbL",
        "generated_at": now.isoformat(),
        "stale_after_hours": 6,
        "default_locality_id": "sivasagar-sibsagar",
        "runtime": read(Path("content/runtime.json")),
        "helplines": read(Path("content/helplines.json"))["numbers"],
        "i18n": {
            "en": read(Path("content/i18n/en.json")),
            "as": read(Path("content/i18n/as.json")),
        },
        "localities": localities["localities"],
        "gauges": gauges,
        "camps": camps,
        "camps_saved_at": camps_saved_at,
        "official_source_url": cwc["source_base_url"],
        "crowd_url": crowd_url,
        "impact_pointer_url": impact_pointer_url,
    }
    bundle_bytes = (
        json.dumps(bundle, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n"
    ).encode()
    bundle_hash = hashlib.sha256(bundle_bytes).hexdigest()
    data_dir = Path("pwa/data")
    bundle_name = f"content-{bundle_hash}.json"
    village_name = f"villages-{village_hash}.json"
    write_immutable(data_dir / bundle_name, bundle_bytes)
    write_immutable(data_dir / village_name, villages_bytes)
    manifest = {
        "schema_version": 1,
        "generated_at": now.isoformat(),
        "content_url": f"data/{bundle_name}",
        "village_index_url": f"data/{village_name}",
    }
    (data_dir / "current.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )


if __name__ == "__main__":
    main()
