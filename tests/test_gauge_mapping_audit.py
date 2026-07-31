"""The distance audit that stands between a district default and a flood alert.

Every revenue circle reads its river level from one assigned gauge. That mapping
is a hydrology judgement, but for most circles it was made by a district-wide
default — and nothing checked whether the default landed in the right basin.
Silonijan shipped reading from Kampur, 101 km away across the Karbi hills, while
a warning-level gauge sat 51 km off on the river that actually drains it. The
bulletin said "Below warning level" in the largest type on the screen.

These tests do not claim to know which gauge is correct. They hold two lines:
a mapping nobody checked may not call itself checked, and a circle far from its
gauge may not leave the review queue quietly.
"""

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bl = _load("build_localities", "build_localities.py")
audit = _load("audit_gauge_mappings", "audit_gauge_mappings.py")


@pytest.fixture(scope="module")
def localities() -> list[dict]:
    return json.loads((ROOT / "config" / "assam-localities.json").read_text())["localities"]


@pytest.fixture(scope="module")
def queue() -> list[dict]:
    path = ROOT / "data" / "review" / "locality-gauge-mappings" / "current.json"
    return json.loads(path.read_text())["records"]


@pytest.fixture(scope="module")
def stations() -> dict:
    return bl.load_station_reference(ROOT / "data")


def test_the_station_reference_is_readable_offline(stations) -> None:
    assert stations, "the audit cannot run without a recorded CWC station reference"
    assert all(row.get("coordinates") for row in stations.values())


def test_committed_registry_matches_the_audit(localities, stations) -> None:
    """The CI guard. Change a mapping without re-auditing and this fails."""
    expected, _ = audit.audited(localities, stations)
    drift = [
        item["locality_id"]
        for item, current in zip(expected, localities, strict=True)
        if item["primary_gauge_mapping"] != current["primary_gauge_mapping"]
    ]
    assert not drift, (
        "gauge mappings are stale — run scripts/audit_gauge_mappings.py --write. "
        f"First few: {drift[:5]}"
    )


def test_every_mapping_records_how_far_its_gauge_is(localities) -> None:
    for row in localities:
        mapping = row["primary_gauge_mapping"]
        assert "distance_km" in mapping, row["locality_id"]
        assert "nearest_gauge_km" in mapping, row["locality_id"]


def test_no_distant_mapping_claims_to_be_reviewed(localities) -> None:
    """The bug this file was written for.

    A district-reassignment tuple used to overwrite the gauge confidence, so
    sixteen circles in the seven post-2011 districts were published as reviewed
    high-confidence matches on the strength of a gazette notification that says
    nothing about rivers. Goreswar (Pt) read from a gauge 78 km away.
    """
    offenders = [
        (row["locality_id"], row["primary_gauge_mapping"]["distance_km"])
        for row in localities
        if row["primary_gauge_mapping"]["reviewed"]
        and (
            row["primary_gauge_mapping"]["far"]
            or row["primary_gauge_mapping"]["much_nearer_gauge_exists"]
        )
    ]
    assert not offenders, f"distant mappings claiming review: {offenders}"


def test_reviewed_means_high_confidence_and_nothing_else(localities) -> None:
    for row in localities:
        mapping = row["primary_gauge_mapping"]
        assert mapping["reviewed"] is (mapping["confidence"] == "high")


def test_every_unverified_mapping_is_in_the_queue(localities, queue) -> None:
    queued = {row["locality_id"] for row in queue}
    unqueued = [
        row["locality_id"]
        for row in localities
        if row["primary_gauge_mapping"]["confidence"] != "high"
        and row["locality_id"] not in queued
    ]
    assert not unqueued, f"unreviewed mappings missing from the review queue: {unqueued}"


def test_the_post_2011_districts_are_back_in_the_queue(localities, queue) -> None:
    """Named explicitly, because these are the ones that silently vanished."""
    queued = {row["locality_id"] for row in queue}
    post_2011 = {
        "Bajali", "Biswanath", "Charaideo", "Hojai",
        "Majuli", "South Salmara-Mankachar", "Tamulpur",
    }
    for row in localities:
        if row["district"] not in post_2011:
            continue
        mapping = row["primary_gauge_mapping"]
        if mapping["confidence"] == "high":
            # Allowed, but only where the mapping table itself says high — not
            # where a district reassignment lent it the word.
            assert audit.claimed_confidence(row) == "high", row["locality_id"]
            continue
        assert row["locality_id"] in queued, row["locality_id"]


def test_silonijan_is_flagged(localities) -> None:
    row = next(r for r in localities if r["locality_id"] == "karbi-anglong-silonijan")
    mapping = row["primary_gauge_mapping"]
    assert mapping["much_nearer_gauge_exists"]
    assert mapping["confidence"] == "unverified"
    assert mapping["distance_km"] > 100
    assert mapping["nearest_gauge_km"] < 50


def test_the_queue_leads_with_the_worst_case(queue) -> None:
    distances = [row["distance_km"] or 0 for row in queue]
    assert distances == sorted(distances, reverse=True)


def test_distance_never_promotes_a_mapping(stations) -> None:
    """A gauge two kilometres away is still not a checked mapping."""
    fabricated = [
        {
            "locality_id": "test-close-but-unchecked",
            "district": "Nagaon",
            "census_2011_district": "Nagaon",
            # Raha takes Nagaon's district default, which the table rates medium.
            # Kampur would prove nothing here: it has its own reviewed override.
            "revenue_circle": "Raha",
            "source_aliases": [],
            "centroid": stations["033-UBDDIB"]["coordinates"],
            "primary_gauge": "033-UBDDIB",
            "primary_gauge_mapping": {"confidence": "medium", "basis": "test"},
        }
    ]
    audited, _ = audit.audited(fabricated, stations)
    mapping = audited[0]["primary_gauge_mapping"]
    assert mapping["distance_km"] == 0.0
    assert mapping["confidence"] != "high"
    assert mapping["reviewed"] is False
