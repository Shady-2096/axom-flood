"""Coverage checks for the supplemental OSM place-name layer."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLACE_KINDS = {
    "city",
    "town",
    "suburb",
    "village",
    "quarter",
    "neighbourhood",
    "hamlet",
    "isolated_dwelling",
}


def latest_payload(prefix: str) -> Path:
    paths = [
        path
        for path in (ROOT / "data" / "reference" / "osm").glob(f"{prefix}-*.json")
        if not path.name.endswith(".metadata.json")
    ]
    assert paths
    return max(paths, key=lambda path: path.stat().st_mtime)


def test_every_named_osm_place_in_the_assam_snapshot_is_assigned() -> None:
    source = json.loads(latest_payload("assam-places").read_text())["elements"]
    candidates = {
        f"{item['type']}/{item['id']}"
        for item in source
        if item.get("tags", {}).get("name")
        and item.get("tags", {}).get("place") in PLACE_KINDS
    }
    places = json.loads(
        (ROOT / "config" / "assam-osm-places.json").read_text()
    )["places"]
    assigned = {item["osm_id"] for item in places}
    assert candidates == assigned


def test_guwahati_city_and_shape_resolve_to_the_guwahati_circle() -> None:
    places = json.loads(
        (ROOT / "config" / "assam-osm-places.json").read_text()
    )["places"]
    guwahati = [item for item in places if item["place_name"] == "Guwahati"]
    assert len(guwahati) == 1
    assert guwahati[0]["locality_ids"] == ["kamrup-metropolitan-guwahati"]

    shapes = json.loads(
        (ROOT / "config" / "assam-circle-shapes.json").read_text()
    )["circles"]
    assert any(
        item["locality_ids"] == ["kamrup-metropolitan-guwahati"]
        and item["revenue_circle"] == "Guwahati"
        for item in shapes
    )
