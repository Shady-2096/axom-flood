"""The packets a reviewer decides gauge topology from.

The distance audit can only demote. Workstream 1 is the human promote path, and
these packets are what the human reads. That makes them safety-critical in a
quiet way: a packet that hides a dead gauge, orders candidates by anything other
than distance, or arrives with a decision already filled in would launder a
machine guess into a reviewed mapping.

These tests hold four lines:

- the packet never decides;
- distance is the only ordering inside a candidate list;
- a gauge that is not reporting is never presented as if it were;
- every claim in the packet names the file it came from.
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


packets_module = _load("build_gauge_decision_packets", "build_gauge_decision_packets.py")

PACKETS = ROOT / "data" / "review" / "gauge-topology" / "current.json"


@pytest.fixture(scope="module")
def document() -> dict:
    if not PACKETS.exists():
        pytest.skip("packets not built yet; run scripts/build_gauge_decision_packets.py")
    return json.loads(PACKETS.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def queue() -> dict:
    return json.loads(
        (ROOT / "data" / "review" / "locality-gauge-mappings" / "current.json").read_text(
            encoding="utf-8"
        )
    )


def test_every_flagged_circle_gets_a_packet(document, queue) -> None:
    flagged = {
        record["locality_id"]
        for record in queue["records"]
        if record.get("far") or record.get("much_nearer_gauge_exists")
    }
    assert {packet["locality_id"] for packet in document["packets"]} == flagged


def test_no_packet_arrives_already_decided(document) -> None:
    """The whole point is that a person decides. Nothing here may pre-empt that."""
    for packet in document["packets"]:
        assert packet["decision"] is None
        assert packet["decision_reasoning"] is None
        assert packet["reviewer"] is None
        assert packet["reviewed_at"] is None


def test_no_suitable_gauge_is_an_allowed_answer(document) -> None:
    assert "no_suitable_gauge_exists" in document["decisions"]["allowed"]


def test_candidates_are_ordered_by_distance_and_nothing_else(document) -> None:
    """Ordering is the quietest way a tool can make a recommendation.

    If matched river names or reporting status floated to the top, the list
    would be a ranking, and a reviewer skimming it would be reading this
    script's opinion rather than the evidence.
    """
    for packet in document["packets"]:
        distances = [row["distance_km"] for row in packet["candidate_gauges"]]
        assert distances == sorted(distances)


def test_a_stopped_gauge_is_never_silently_offered(document) -> None:
    for packet in document["packets"]:
        for row in packet["candidate_gauges"]:
            assert row["station_operational"] is not None


def test_the_river_match_is_labelled_as_a_name_comparison(document) -> None:
    """The flag is a string match between two name lists, and must read as one."""
    doc = (ROOT / "docs" / "gauge-topology-questions.md").read_text(encoding="utf-8")
    assert "string comparison" in doc
    assert "not an answer" in doc


def test_river_names_carry_their_licence(document) -> None:
    assert "OpenStreetMap" in document["attribution"]
    assert "ODbL" in document["attribution"]


def test_provenance_names_every_input(document) -> None:
    provenance = document["provenance"]
    for key in ("flagged_from", "localities", "station_reference", "circle_outlines"):
        assert provenance[key], f"{key} is not recorded"
        assert (ROOT / provenance[key]).exists()


def test_a_missing_waterway_snapshot_is_recorded_not_hidden(document) -> None:
    """An absent snapshot is a legitimate state; an unlabelled one is not."""
    reference = document["provenance"]["waterway_snapshot"]
    if reference is None:
        for packet in document["packets"]:
            assert packet["rivers_over_circle"] == []
            assert packet["rivers_over_circle_method"] == "no_snapshot"
    else:
        assert (ROOT / reference).exists()


def test_high_priority_means_both_flags(document) -> None:
    for packet in document["packets"]:
        both = packet["flagged_far"] and packet["flagged_much_nearer_exists"]
        assert packet["priority"] == ("high" if both else "normal")


def test_high_priority_packets_come_first(document) -> None:
    priorities = [packet["priority"] for packet in document["packets"]]
    assert priorities == sorted(priorities, key=lambda value: value != "high")


def test_silonijan_is_in_the_queue(document) -> None:
    """The case that started the workstream."""
    silonijan = next(
        packet
        for packet in document["packets"]
        if packet["locality_id"] == "karbi-anglong-silonijan"
    )
    assert silonijan["priority"] == "high"
    assert silonijan["assigned_gauge"]["distance_km"] > 100


def test_river_name_folding_ignores_spelling_noise_only() -> None:
    fold = packets_module.fold_river
    assert fold("Kopili") == fold("kopili")
    assert fold("Jatinga River") == fold("Jatinga")
    assert fold("Puthimari Nadi") == fold("Puthimari")
    # Different rivers must not fold together, or the match flag becomes noise.
    assert fold("Beki") != fold("Barak")
    assert fold(None) == ""


def test_a_qualified_river_name_still_matches_the_plain_one() -> None:
    """The Silonijan case: OSM's "Dhansiri River" against CWC's "Dhansiri (South)".

    Exact equality left the one circle this workstream exists for showing no
    connection to the gauge 21 km away on its own river.
    """
    agree = packets_module.river_names_agree
    fold = packets_module.fold_river
    circle = {fold("Dhansiri River"), fold("Kaliyani"), fold("Deopani Nadi")}
    assert agree("Dhansiri (South)", circle)
    assert not agree("Kopili", circle)
    assert not agree(None, circle)
    assert not agree("Dhansiri", set())


def test_upstream_pairs_arrive_undecided(document) -> None:
    for row in document["upstream_pairs"]:
        assert row["decision"] is None
        assert row["reviewer"] is None
        assert row["reviewed_at"] is None


def test_a_pair_that_failed_its_own_gates_is_never_asked_as_a_question(document) -> None:
    """Weak evidence produces no sentence, per the plan's own rule.

    Carrying it into the worksheet as a question would spend a reviewer's
    attention on a pair we could not use whatever they answered.
    """
    doc = (ROOT / "docs" / "gauge-topology-questions.md").read_text(encoding="utf-8")
    withheld = [
        row
        for row in document["upstream_pairs"]
        if not row["evidence"]["passes_quality_gates"]
    ]
    if not withheld:
        pytest.skip("every candidate pair passed its quality gates")
    assert "Not asking about these" in doc
    for row in withheld:
        pair = f"{row['upstream']['site_name']} → {row['downstream']['site_name']}"
        before, _, after = doc.partition("## Not asking about these")
        assert pair in after and f"### {pair}" not in before


def test_the_worksheet_says_matching_timing_is_not_proof(document) -> None:
    """The shared-rainfall confound is the whole reason a person is being asked."""
    if not document["upstream_pairs"]:
        pytest.skip("no upstream candidates on disk")
    doc = (ROOT / "docs" / "gauge-topology-questions.md").read_text(encoding="utf-8")
    assert "not proof" in doc
    assert "same rain fell on both" in doc


def test_lag_is_shown_as_a_range_not_a_single_hour(document) -> None:
    """A single-hour figure would claim precision the method does not have."""
    for row in document["upstream_pairs"]:
        low, high = row["evidence"]["observed_yearly_lag_range_hours"]
        assert low <= row["evidence"]["recommended_lag_hours"] <= high


def test_silonijan_packet_points_at_its_own_river(document) -> None:
    """End to end: the case that started the workstream must not stay dark."""
    packet = next(
        item
        for item in document["packets"]
        if item["locality_id"] == "karbi-anglong-silonijan"
    )
    if not packet["rivers_over_circle"]:
        pytest.skip("no waterway snapshot; the river comparison cannot run")
    matched = [
        row
        for row in packet["candidate_gauges"]
        if row["river_name_also_over_circle"] and row["station_operational"]
    ]
    assert matched, "no reporting gauge shares a river name with Silonijan"
    assert not packet["assigned_gauge"]["river_name_also_over_circle"]
