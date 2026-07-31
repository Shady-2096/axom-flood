"""Tests for district resolution in the Phase 1 locality registry.

Eight of Assam's 35 districts postdate the 2011 Census, so the Census workbook
files their revenue circles under the parent district they were carved from.
A user in Biswanath should not have to know to look under Sonitpur, but a circle
put in the wrong district routes their flood alert to the wrong place — so every
reassignment here is evidence-backed and the one district without evidence stays
unassigned on purpose.
"""

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "build_localities", ROOT / "scripts" / "build_localities.py"
)
bl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bl)


@pytest.fixture(scope="module")
def localities() -> list[dict]:
    return json.loads((ROOT / "config" / "assam-localities.json").read_text())["localities"]


@pytest.fixture(scope="module")
def canonical_districts() -> set[str]:
    registry = json.loads((ROOT / "config" / "assam-districts.json").read_text())
    return {entry["name"] for entry in registry["districts"]}


def test_every_reassignment_target_is_a_canonical_district(canonical_districts) -> None:
    for (_census, _circle), (target, _url, _confidence) in bl.DISTRICT_REASSIGNMENTS.items():
        assert target in canonical_districts, f"{target!r} is not a real district"


def test_every_reassignment_carries_its_evidence() -> None:
    """A district assignment without a source is a guess, and guesses misroute alerts."""
    for key, (_target, url, confidence) in bl.DISTRICT_REASSIGNMENTS.items():
        assert url and url.startswith("https://"), f"{key} has no evidence URL"
        assert confidence in {"high", "medium", "unverified"}


def test_reassignment_is_keyed_on_the_census_parent_not_the_circle_name() -> None:
    """The Census splits circles across districts with a "(Pt)" suffix.

    "Bajali (Pt)" exists under both Barpeta and Baksa. Bajali district was carved
    from Barpeta only, so the Baksa-side part must stay in Baksa. Keying on the
    name alone would move both.
    """
    assert ("Barpeta", "Bajali (Pt)") in bl.DISTRICT_REASSIGNMENTS
    assert ("Baksa", "Bajali (Pt)") not in bl.DISTRICT_REASSIGNMENTS


def test_baksa_side_part_circles_stay_in_baksa(localities) -> None:
    baksa_bajali = [
        row
        for row in localities
        if row["census_2011_district"] == "Baksa" and row["revenue_circle"] == "Bajali (Pt)"
    ]
    assert baksa_bajali, "fixture expectation: Baksa has a Bajali (Pt) circle"
    for row in baksa_bajali:
        assert row["district"] == "Baksa"
        assert row["district_assignment"]["method"] == "census_2011_parent"


def test_post_2011_districts_are_now_their_own_label(localities) -> None:
    by_district: dict[str, set[str]] = {}
    for row in localities:
        by_district.setdefault(row["district"], set()).add(row["revenue_circle"])
    expected = {
        "Bajali": {"Bajali (Pt)", "Sarupeta (Pt)"},
        "Biswanath": {"Biswanath", "Gohpur", "Helem", "Na-Duar"},
        "Charaideo": {"Mahmora", "Sonari"},
        "Hojai": {"Doboka", "Hojai", "Lanka"},
        "Majuli": {"Majuli"},
        "South Salmara-Mankachar": {"Mankachar", "South Salmara"},
        "Tamulpur": {"Goreswar (Pt)", "Tamulpur"},
    }
    for district, circles in expected.items():
        assert by_district.get(district) == circles, district


def test_barnagar_was_not_moved_without_evidence(localities) -> None:
    """The Bajali administration's site never names Barnagar as one of its circles."""
    barnagar = [row for row in localities if row["revenue_circle"] == "Barnagar (Pt)"]
    assert barnagar
    assert all(row["district"] != "Bajali" for row in barnagar)


def test_the_unevidenced_district_is_declared_not_hidden(localities) -> None:
    document = json.loads((ROOT / "config" / "assam-localities.json").read_text())
    gaps = document["provenance"]["districts_without_evidenced_circles"]
    assert "West Karbi Anglong" in gaps
    assert gaps["West Karbi Anglong"]["source_checked"].startswith("https://")
    assert gaps["West Karbi Anglong"]["reason"]
    # And it genuinely has no localities, rather than being quietly populated.
    assert not [row for row in localities if row["district"] == "West Karbi Anglong"]


def test_thirty_four_of_thirty_five_districts_are_represented(
    localities, canonical_districts
) -> None:
    present = {row["district"] for row in localities}
    missing = canonical_districts - present
    assert missing == {"West Karbi Anglong"}, f"unexpected gaps: {sorted(missing)}"


def test_sribhumi_uses_one_spelling_everywhere(localities) -> None:
    """The gauge feed says Sribhumi; the Census workbook says Karimganj."""
    former = [row for row in localities if row["census_2011_district"] == "Karimganj"]
    assert former
    for row in former:
        assert row["district"] == "Sribhumi"
        assert row["district_slug"] == "sribhumi"
        # Kept stable because the PWA and published bundles key on it.
        assert row["locality_id"].startswith("karimganj-")


def test_kampur_is_untouched(localities) -> None:
    kampur = [row for row in localities if row["locality_id"] == "nagaon-kampur"][0]
    assert kampur["district"] == "Nagaon"
    assert kampur["district_assignment"]["method"] == "census_2011_parent"
    assert kampur["primary_gauge"] == "033-UBDDIB"


def test_current_guwahati_revenue_circle_is_present_and_sourced(localities) -> None:
    guwahati = [
        row for row in localities
        if row["locality_id"] == "kamrup-metropolitan-guwahati"
    ]
    assert len(guwahati) == 1
    locality = guwahati[0]
    assert locality["revenue_circle"] == "Guwahati"
    assert locality["district"] == "Kamrup Metropolitan"
    assert locality["census_2011_district"] is None
    assert locality["district_assignment"] == {
        "method": "current_district_administration",
        "source_url": "https://kamrupmetro.assam.gov.in/about-us/about-district",
        "confidence": "high",
        "reviewed": True,
    }
    assert locality["primary_gauge"] == "001-MBDGHY"
