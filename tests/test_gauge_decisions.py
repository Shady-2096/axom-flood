"""The reviewed promote path, and the limits on it.

The distance audit can only demote, and that stays true. This is the other
direction: a person who knows Assam's rivers answers, per circle, whether the
assigned gauge sits on water that reaches it. Their answer is the only thing in
this project that can call a mapping reviewed.

These tests hold four lines:

- a decision without a name, a qualification, and a reason is not a decision;
- a reassign may not point at a gauge that does not exist or has stopped
  reporting;
- a reviewed circle stops being demoted by distance, because the reviewer saw
  the distance before deciding;
- "no gauge fits" produces a circle with no gauge, not a circle quietly still
  reading the wrong river.
"""

import importlib.util
import json
from pathlib import Path

import pytest

from axom_flood.gauges import decisions as gd

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
def stations() -> dict:
    return bl.load_station_reference(ROOT / "data")


def write(tmp_path: Path, rows: list[dict]) -> Path:
    path = tmp_path / "decisions.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "record": "gauge_topology_decisions",
                "provenance": {"note": "test"},
                "decisions": rows,
            }
        )
    )
    return path


def row(**overrides) -> dict:
    base = {
        "locality_id": "karbi-anglong-silonijan",
        "decision": "reassign",
        "primary_gauge": "023-UBDDIB",
        "basis": "Dhansiri (South) at Bokajan",
        "decision_reasoning": "The Dhansiri drains this circle; the Kopili does not.",
        "reviewer": "A. Reviewer",
        "reviewer_qualification": "Knows Assam's rivers. Not a hydrologist.",
        "reviewed_at": "2026-08-01",
    }
    base.update(overrides)
    return {key: value for key, value in base.items() if value is not None}


# --- the record has to be a record ---------------------------------------


@pytest.mark.parametrize(
    "field",
    ["reviewer", "reviewer_qualification", "decision_reasoning", "basis", "reviewed_at"],
)
def test_a_decision_without_its_author_or_reason_is_refused(tmp_path, field) -> None:
    """An anonymous decision cannot be re-examined, so it cannot be trusted."""
    with pytest.raises(gd.DecisionError, match=field):
        gd.load(write(tmp_path, [row(**{field: None})]))


def test_the_vocabulary_is_closed(tmp_path) -> None:
    with pytest.raises(gd.DecisionError, match="not one of"):
        gd.load(write(tmp_path, [row(decision="probably_fine")]))


def test_a_circle_cannot_be_decided_twice(tmp_path) -> None:
    with pytest.raises(gd.DecisionError, match="decided twice"):
        gd.load(write(tmp_path, [row(), row(decision="keep", primary_gauge=None)]))


def test_a_reassign_must_name_the_replacement(tmp_path) -> None:
    with pytest.raises(gd.DecisionError, match="must name the gauge"):
        gd.load(write(tmp_path, [row(primary_gauge=None)]))


def test_no_suitable_gauge_cannot_also_name_a_gauge(tmp_path) -> None:
    with pytest.raises(gd.DecisionError, match="cannot also name a gauge"):
        gd.load(write(tmp_path, [row(decision="no_suitable_gauge_exists")]))


def test_a_missing_record_is_no_decisions_not_a_crash(tmp_path) -> None:
    assert gd.load(tmp_path / "absent.json") == {}


# --- the decision has to be applicable ------------------------------------


def test_an_unknown_circle_is_reported_not_ignored(tmp_path, localities, stations) -> None:
    decisions = gd.load(write(tmp_path, [row(locality_id="atlantis-ward-3")]))
    assert gd.problems(decisions, localities, stations) == [
        "atlantis-ward-3: no such circle in the locality registry"
    ]


def test_a_reassign_to_an_unknown_station_is_refused(tmp_path, localities, stations) -> None:
    decisions = gd.load(write(tmp_path, [row(primary_gauge="999-NOWHERE")]))
    faults = gd.problems(decisions, localities, stations)
    assert faults and "not in the CWC station reference" in faults[0]


def test_a_reassign_to_a_stopped_gauge_points_at_the_right_answer(
    tmp_path, localities, stations
) -> None:
    """A dead gauge on the correct river is no_suitable_gauge_exists.

    Reassigning to it would put the circle back to showing nothing, but under a
    label claiming a reviewed gauge — the worst of both.
    """
    stopped = next(
        code
        for code, station in stations.items()
        if station.get("station_operational") is False
    )
    decisions = gd.load(write(tmp_path, [row(primary_gauge=stopped)]))
    faults = gd.problems(decisions, localities, stations)
    assert faults and "no_suitable_gauge_exists, not a reassign" in faults[0]


def test_a_keep_cannot_smuggle_in_a_different_gauge(tmp_path, localities, stations) -> None:
    decisions = gd.load(
        write(tmp_path, [row(locality_id="nagaon-kampur", decision="keep")])
    )
    faults = gd.problems(decisions, localities, stations)
    assert faults and "Use reassign to change the gauge" in faults[0]


def test_a_sound_decision_has_no_problems(tmp_path, localities, stations) -> None:
    decisions = gd.load(write(tmp_path, [row()]))
    assert gd.problems(decisions, localities, stations) == []


# --- what applying one does ------------------------------------------------


def by_id(localities: list[dict], locality_id: str) -> dict:
    return next(item for item in localities if item["locality_id"] == locality_id)


def test_a_reviewed_circle_is_no_longer_demoted_by_distance(
    tmp_path, localities, stations
) -> None:
    """Silonijan's own case, with the gauge it was flagged for.

    Reviewing it and then having the nightly audit demote it again would mean
    the answer never survives to a reader.
    """
    decisions = gd.load(write(tmp_path, [row()]))
    updated, queue = audit.audited(localities, stations, decisions)
    circle = by_id(updated, "karbi-anglong-silonijan")
    assert circle["primary_gauge"] == "023-UBDDIB"
    mapping = circle["primary_gauge_mapping"]
    assert mapping["confidence"] == "high"
    assert mapping["reviewed"] is True
    assert mapping["method"] == gd.REVIEWED_METHOD
    assert "karbi-anglong-silonijan" not in {item["locality_id"] for item in queue}


def test_the_reviewer_and_their_real_qualification_travel_with_the_mapping(
    tmp_path, localities, stations
) -> None:
    """Never written up as a hydrologist sign-off. It is whatever they said it is."""
    decisions = gd.load(write(tmp_path, [row()]))
    updated, _ = audit.audited(localities, stations, decisions)
    review = by_id(updated, "karbi-anglong-silonijan")["primary_gauge_mapping"]["review"]
    assert review["reviewer"] == "A. Reviewer"
    assert review["reviewer_qualification"] == "Knows Assam's rivers. Not a hydrologist."
    assert review["reasoning"]
    assert review["reviewed_at"] == "2026-08-01"
    assert review["decision"] == "reassign"


def test_no_suitable_gauge_leaves_the_circle_with_no_gauge_at_all(
    tmp_path, localities, stations
) -> None:
    decisions = gd.load(
        write(
            tmp_path,
            [
                row(
                    locality_id="dima-hasao-mahur",
                    decision="no_suitable_gauge_exists",
                    primary_gauge=None,
                    basis="No reporting gauge sits on this circle's drainage",
                )
            ],
        )
    )
    updated, queue = audit.audited(localities, stations, decisions)
    circle = by_id(updated, "dima-hasao-mahur")
    # The point of the whole outcome: it stops reading the wrong river rather
    # than keeping a number nobody should act on.
    assert circle["primary_gauge"] is None
    mapping = circle["primary_gauge_mapping"]
    assert mapping["confidence"] == gd.NO_GAUGE_CONFIDENCE
    assert mapping["confidence"] not in {"high", "medium", "unverified"}
    assert mapping["reviewed"] is True
    assert "dima-hasao-mahur" not in {item["locality_id"] for item in queue}


def test_the_distance_facts_survive_the_decision(tmp_path, localities, stations) -> None:
    """A reviewed mapping is exempt from the demotion, not from the measurement."""
    decisions = gd.load(write(tmp_path, [row()]))
    updated, _ = audit.audited(localities, stations, decisions)
    mapping = by_id(updated, "karbi-anglong-silonijan")["primary_gauge_mapping"]
    for field in ("distance_km", "nearest_gauge", "nearest_gauge_km", "far",
                  "much_nearer_gauge_exists"):
        assert field in mapping


def test_an_undecided_circle_is_still_demoted(localities, stations) -> None:
    """The audit's demote-only behaviour is untouched where nobody has decided."""
    updated, queue = audit.audited(localities, stations, {})
    flagged = [item for item in queue if item["far"] or item["much_nearer_gauge_exists"]]
    assert flagged, "fixture expectation: distance still flags circles"
    for item in updated:
        mapping = item["primary_gauge_mapping"]
        if mapping.get("far") or mapping.get("much_nearer_gauge_exists"):
            assert mapping["confidence"] == "unverified"


def test_the_committed_record_is_valid_even_while_empty(localities, stations) -> None:
    """The real file, whatever is in it, must always be applicable."""
    decisions = gd.load(audit.DECISIONS)
    assert gd.problems(decisions, localities, stations) == []
