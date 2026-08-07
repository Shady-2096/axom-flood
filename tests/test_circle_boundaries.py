"""Tests for revenue-circle boundary matching, scoring, and topology."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from axom_flood.boundaries.osm import (
    Relation,
    assign_districts,
    circle_key,
    district_matches,
    load_relations,
    match_localities,
    stitch_rings,
)
from axom_flood.boundaries.quality import (
    MIN_POINTS_FOR_A_SCORE,
    TOLERANCE_KM,
    CircleScore,
    cell_area_sq_km,
    measure_topology,
    rasterize,
    school_points_by_locality,
    score_circle,
    village_counts,
)

ROOT = Path(__file__).resolve().parents[1]
REVIEW = ROOT / "data" / "review" / "circle-boundaries" / "current.json"


def square(x0: float, y0: float, size: float) -> list[list[float]]:
    return [[x0, y0], [x0 + size, y0], [x0 + size, y0 + size], [x0, y0 + size], [x0, y0]]


def locality(locality_id: str, circle: str, district: str) -> dict:
    return {"locality_id": locality_id, "revenue_circle": circle, "district": district}


def test_circle_key_folds_the_part_suffix_but_not_the_name():
    assert circle_key("Dhekiajuli (Pt)") == circle_key("Dhekiajuli tehsil") == "dhekiajuli"
    assert circle_key("Subansiri (Pt-I)") == circle_key("Subansiri (Pt II)") == "subansiri"
    assert circle_key("Lakhipur") != circle_key("Lakhimpur")


def test_district_succession_recognises_land_under_its_new_name():
    # Bajali was carved out of Barpeta in 2020, so a circle the Census files
    # under Barpeta may sit inside OSM's Bajali.
    assert district_matches("Barpeta", "Bajali")
    assert district_matches("Karbi Anglong", "West Karbi Anglong")
    # Succession is one-directional: the parent does not stand in for the child.
    assert not district_matches("Bajali", "Barpeta")
    # Districts that were always separate never match.
    assert not district_matches("Goalpara", "Cachar")


def test_district_alias_covers_a_renamed_district():
    # Karimganj became Sribhumi in 2024; OSM still carries the old name.
    assert district_matches("Sribhumi", "Karimganj")


def test_stitch_rings_joins_reversed_and_unordered_ways():
    members = [
        {"type": "way", "role": "outer", "geometry": [
            {"lon": 0.0, "lat": 0.0}, {"lon": 1.0, "lat": 0.0}]},
        # Deliberately reversed, and given out of order.
        {"type": "way", "role": "outer", "geometry": [
            {"lon": 0.0, "lat": 1.0}, {"lon": 1.0, "lat": 1.0}]},
        {"type": "way", "role": "outer", "geometry": [
            {"lon": 1.0, "lat": 0.0}, {"lon": 1.0, "lat": 1.0}]},
        {"type": "way", "role": "outer", "geometry": [
            {"lon": 0.0, "lat": 1.0}, {"lon": 0.0, "lat": 0.0}]},
    ]
    rings = stitch_rings(members)
    assert len(rings) == 1
    assert rings[0][0] == rings[0][-1]
    assert len(rings[0]) == 5


def test_a_unique_circle_name_matches_without_needing_the_district():
    # The locality file and OSM disagree about Na-Duar's district — the Census
    # files it under Biswanath, OSM draws it inside Sonitpur. There is only one
    # Na-Duar in Assam, so that disagreement is a label, not an ambiguity.
    circles = [Relation(1, "Na-Duar", "6", [square(92.0, 26.0, 0.1)], district="Sonitpur")]
    result = match_localities([locality("x", "Na-Duar", "Biswanath")], circles)
    assert result.matched["x"].osm_id == 1
    assert not result.unresolved


def test_a_split_circle_is_resolved_by_district_not_by_name():
    circles = [
        Relation(1, "Dhekiajuli tehsil", "6", [square(92.0, 26.6, 0.1)], district="Udalguri"),
        Relation(2, "Dhekiajuli (Pt)", "6", [square(92.5, 26.6, 0.1)], district="Sonitpur"),
    ]
    localities = [
        locality("udalguri-dhekiajuli-pt", "Dhekiajuli (Pt)", "Udalguri"),
        locality("sonitpur-dhekiajuli-pt", "Dhekiajuli (Pt)", "Sonitpur"),
    ]
    result = match_localities(localities, circles)
    # The bug this replaces gave both halves the same outline and dropped the other.
    assert result.matched["udalguri-dhekiajuli-pt"].osm_id == 1
    assert result.matched["sonitpur-dhekiajuli-pt"].osm_id == 2


def test_two_different_circles_sharing_a_name_are_kept_apart():
    # Lakhipur is a circle in Goalpara and a different circle in Cachar.
    circles = [
        Relation(1, "Lakhipur", "6", [square(90.6, 26.0, 0.1)], district="Goalpara"),
        Relation(2, "Lakhipur", "6", [square(92.8, 24.8, 0.1)], district="Cachar"),
    ]
    localities = [
        locality("goalpara-lakhipur", "Lakhipur", "Goalpara"),
        locality("cachar-lakhipur", "Lakhipur", "Cachar"),
    ]
    result = match_localities(localities, circles)
    assert result.matched["goalpara-lakhipur"].osm_id == 1
    assert result.matched["cachar-lakhipur"].osm_id == 2


def test_an_ambiguous_split_is_reported_rather_than_guessed():
    circles = [
        Relation(1, "Rangia (Pt)", "6", [square(91.6, 26.4, 0.02)], district="Kamrup"),
        Relation(2, "Rangia Pt", "6", [square(91.5, 26.5, 0.1)], district="Kamrup"),
    ]
    result = match_localities([locality("kamrup-rangia-pt", "Rangia (Pt)", "Kamrup")], circles)
    assert "kamrup-rangia-pt" not in result.matched
    assert result.unresolved[0]["reason"] == "several_relations_in_the_same_district"
    assert len(result.unresolved[0]["candidates"]) == 2


def test_a_name_that_does_not_exist_is_reported_not_dropped():
    result = match_localities([locality("x", "Nowhere", "Cachar")], [])
    assert result.unresolved[0]["reason"] == "no_relation_with_this_name"


def test_a_circle_is_assigned_to_the_district_holding_most_of_its_vertices():
    # A circle with a long thin arm reaching into the neighbouring district.
    # Most of it is in Left; a single interior point chosen from the arm would
    # say Right. Kaliabor, which wraps around the Kolong, resolved to Karbi
    # Anglong exactly that way before the count replaced the single point.
    arm = [[0.0, 0.0], [0.5, 0.0], [1.0, 0.0], [1.4, 0.0],
           [3.0, 0.4], [3.0, 0.6],
           [1.4, 1.0], [1.0, 1.0], [0.5, 1.0], [0.0, 1.0], [0.0, 0.0]]
    left = Relation(10, "Left", "5", [square(-0.5, -0.5, 2.0)])
    right = Relation(11, "Right", "5", [square(1.5, -0.5, 2.0)])
    circle = Relation(1, "Arm", "6", [arm])
    assign_districts([circle], [left, right], stride=1)
    assert circle.district == "Left"
    assert circle.district_share > 0.5


def test_load_relations_skips_relations_with_no_closed_ring():
    elements = [
        {"id": 1, "type": "relation", "tags": {"admin_level": "6", "name": "Broken"},
         "members": [{"type": "way", "role": "outer",
                      "geometry": [{"lon": 0.0, "lat": 0.0}, {"lon": 1.0, "lat": 0.0}]}]},
        {"id": 2, "type": "relation", "tags": {"admin_level": "8", "name": "Too small"},
         "members": []},
    ]
    districts, circles = load_relations(elements)
    assert districts == []
    assert circles == []


def test_score_counts_only_points_inside():
    rings = [square(0.0, 0.0, 1.0)]
    points = [(0.5, 0.5), (0.2, 0.9), (5.0, 5.0)]
    score = score_circle("x", rings, points, villages=2)
    assert score.points == 3
    assert score.inside == 2
    assert score.agreement_strict == pytest.approx(2 / 3)
    # 5 degrees out is far past any tolerance, so the tolerant share agrees.
    assert score.agreement == pytest.approx(2 / 3)
    assert not score.has_enough_points


def test_a_circle_with_no_points_has_no_agreement():
    assert score_circle("x", [square(0.0, 0.0, 1.0)], []).agreement is None


def test_a_point_just_outside_the_line_is_not_counted_as_disagreement():
    """The whole reason the tolerance exists.

    A school 300 m over a shared border and a school 76 km away used to score
    identically. For averaging rainfall over a few hundred square kilometres,
    the first is not evidence of a wrong outline.
    """

    rings = [square(0.0, 26.0, 1.0)]
    just_outside = (1.003, 26.5)  # ~300 m east of the edge
    score = score_circle("x", rings, [(0.5, 26.5), just_outside])

    assert score.inside == 1
    assert score.within_tolerance == 2
    assert score.agreement == pytest.approx(1.0)
    # Published side by side, so the tolerance never has to be taken on trust.
    assert score.agreement_strict == pytest.approx(0.5)
    assert score.stray_distances_km == ()


def test_a_point_well_outside_still_counts_against_the_circle():
    rings = [square(0.0, 26.0, 1.0)]
    far = (1.1, 26.5)  # ~10 km east of the edge
    score = score_circle("x", rings, [(0.5, 26.5), far])

    assert score.within_tolerance == 1
    assert score.agreement == pytest.approx(0.5)
    assert score.max_stray_km == pytest.approx(10.0, abs=0.5)


def test_stray_distance_is_reported_for_a_point_nowhere_near_the_circle():
    """A point far enough out to reject every segment still gets a real number.

    The fast pass skips segments beyond the tolerance, so a distant point rejects
    all of them. Reporting that as zero — or as infinity — would make the one
    signal that separates a border dispute from a bad join useless.
    """

    rings = [square(0.0, 26.0, 1.0)]
    score = score_circle("x", rings, [(3.0, 26.5)])

    assert score.max_stray_km is not None
    assert 190 < score.max_stray_km < 210  # ~2 degrees of longitude at 26°N


def test_the_tolerant_count_is_never_below_the_strict_one():
    """A disagreement between the distance measure and the containment test is a
    bug in this module, not a low score, so it cannot be published as one."""

    score = CircleScore(
        locality_id="x", points=10, inside=8, villages=0, within_tolerance=3
    )
    assert score.within_tolerance == 8


def test_village_counts_ignore_centres_derived_from_the_circle():
    index = [
        {"locality_id": "a", "centre_confidence": "exact_village_school_median"},
        {"locality_id": "a", "centre_confidence": "revenue_circle_fallback"},
        {"locality_id": "b", "centre_confidence": "revenue_circle_fallback"},
    ]
    assert village_counts(index) == {"a": 1}


def test_school_points_drop_a_village_name_shared_by_two_circles(tmp_path):
    index = [
        {"locality_id": "a", "district": "Cachar", "village_name": "Solo"},
        {"locality_id": "a", "district": "Cachar", "village_name": "Shared"},
        {"locality_id": "b", "district": "Cachar", "village_name": "Shared"},
    ]
    csv_path = tmp_path / "schools.csv"
    csv_path.write_text(
        "district,village,longitude,latitude\n"
        "CACHAR,Solo,92.8,24.8\n"
        "CACHAR,Shared,92.9,24.9\n"
    )
    points = school_points_by_locality(index, csv_path)
    assert points == {"a": [(92.8, 24.8)]}


def test_rasterize_fills_the_interior_and_stops_at_the_edge():
    cells = rasterize([square(0.0, 0.0, 0.05)], step=0.005)
    # A 0.05-degree square holds 10 by 10 cell centres.
    assert len(cells) == 100
    assert all(0 <= column < 10 and 0 <= row < 10 for column, row in cells)


def test_touching_circles_do_not_register_as_overlapping():
    # Two circles sharing an entire border. A vertex-based test called this an
    # overlap for 431 pairs; cell centres cannot land on a border of zero width.
    outlines = {
        "left": [square(0.0, 0.0, 0.05)],
        "right": [square(0.05, 0.0, 0.05)],
    }
    _, shared = measure_topology(outlines, step=0.005)
    assert shared == {}


def test_a_genuine_overlap_is_reported_for_both_circles():
    outlines = {
        "left": [square(0.0, 0.0, 0.05)],
        "right": [square(0.02, 0.0, 0.05)],
    }
    cells, shared = measure_topology(outlines, step=0.005)
    assert shared["left"]["right"] == shared["right"]["left"] > 0
    assert cells["left"] & cells["right"]


def test_cell_area_shrinks_towards_the_north():
    south = cell_area_sq_km(int(24.0 / 0.005))
    north = cell_area_sq_km(int(28.0 / 0.005))
    assert south > north > 0


class TestPublishedQualityRecord:
    """The committed artifact has to keep saying what it claims to say."""

    @pytest.fixture(scope="class")
    def review(self):
        if not REVIEW.exists():
            pytest.skip("boundary quality record has not been built")
        return json.loads(REVIEW.read_text())

    def test_every_locality_has_a_record(self, review):
        localities = json.loads((ROOT / "config" / "assam-localities.json").read_text())
        ids = {item["locality_id"] for item in localities["localities"]}
        assert {record["locality_id"] for record in review["records"]} == ids

    def test_a_passing_circle_states_its_evidence(self, review):
        passing = [record for record in review["records"] if record["grade"] == "zonal"]
        assert passing, "no circle passed, so the artifact proves nothing"
        for record in passing:
            assert record["agreement"] >= review["rules"]["pass_agreement"]
            assert record["independent_points"] >= review["rules"]["min_independent_points"]
            assert record["overlap_share"] <= review["rules"]["max_overlap_share"]
            assert record["osm_id"].startswith("relation/")

    def test_a_failing_circle_says_why(self, review):
        for record in review["records"]:
            if record["grade"] == "none":
                assert record.get("blocked_by"), record["locality_id"]

    def test_the_grade_records_what_it_does_not_permit(self, review):
        forbids = review["rules"]["grade_zonal_forbids"]
        assert "individual" in forbids

    def test_min_points_matches_the_module(self, review):
        assert review["rules"]["min_independent_points"] == MIN_POINTS_FOR_A_SCORE

    def test_the_tolerance_is_recorded_with_its_reason(self, review):
        assert review["rules"]["agreement_tolerance_m"] == round(TOLERANCE_KM * 1000)
        assert review["rules"]["agreement_tolerance_reason"]

    def test_both_agreement_numbers_are_published(self, review):
        """A tolerant share on its own asks to be trusted. The strict one beside
        it means a reader can check what the tolerance actually bought."""

        scored = [r for r in review["records"] if r.get("agreement") is not None]
        assert scored
        for record in scored:
            assert record["agreement_strict"] is not None, record["locality_id"]
            assert record["agreement"] >= record["agreement_strict"], record["locality_id"]
            assert record["tolerance_m"] == round(TOLERANCE_KM * 1000)

    def test_no_stray_distance_is_infinite(self, review):
        """`Infinity` is not valid JSON, and a distance nothing measured is not a
        distance. This caught a real leak: the fast pass rejected every segment
        for a point far outside, and the fallback never ran."""

        raw = REVIEW.read_text()
        assert "Infinity" not in raw and "NaN" not in raw
        for record in review["records"]:
            for key in ("median_stray_km", "max_stray_km"):
                value = record.get(key)
                assert value is None or 0.0 <= value < 1000, (record["locality_id"], key)


def test_an_exact_district_beats_a_succession_district():
    # North Guwahati is split between Kamrup and Kamrup Metropolitan, and Kamrup
    # Metropolitan was carved out of Kamrup. Succession alone would call both
    # halves a match for a locality filed under Kamrup.
    circles = [
        Relation(1, "North Guwahati (Pt)", "6", [square(91.7, 26.2, 0.05)], district="Kamrup"),
        Relation(
            2, "North Guwahati (Pt)", "6", [square(91.8, 26.2, 0.05)],
            district="Kamrup Metropolitan",
        ),
    ]
    result = match_localities(
        [locality("kamrup-north-guwahati-pt", "North Guwahati (Pt)", "Kamrup")], circles
    )
    assert result.matched["kamrup-north-guwahati-pt"].osm_id == 1
