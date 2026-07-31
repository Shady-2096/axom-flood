from pathlib import Path

import pytest

from axom_flood.asdma.impact import ImpactParseError, extract_impact_sections
from axom_flood.asdma.parser import parse_bulletin, parse_extracted_tables


def test_parse_extracted_tables_extracts_required_totals_and_districts() -> None:
    table = [
        [
            "District\nAffected",
            "No. of",
            "Name of Affected Districts",
            None,
            None,
            None,
            None,
            None,
        ],
        [None, "2", "Sivasagar, Charaideo", None, None, None, None, None],
        ["No. Of\nRevenue\nCircles\nAffected", "3", None, None, None, None, None, None],
        ["Name Of\nRevenue\nCircle\nAffected", "District", "Total", "Revenue Circle"],
        [None, "Sivasaga\nr", "2", "Nazira, Demow"],
        [None, "Total", "3", ""],
        ["Villages\nAffected", "District", "Total", "Revenue Circle"],
        [None, "Sivasaga\nr", "10", ""],
        [None, "Total", "12", ""],
        [
            "Population\nAnd Crop\nArea\nSubmerged",
            "District",
            "Male",
            "Female",
            "Children",
            "Total",
            "Total Crop Area (in Hect.)",
        ],
        [None, "Sivasaga\nr", "40", "40", "20", "100", "25.5"],
        [None, "Total", "50", "50", "25", "125", "30.5"],
        [
            "Relief\nCamps /\nCentres\nOpened",
            "District",
            "Total",
            "Relief Camp",
            None,
            None,
            None,
            "Relief Distribution Centres",
        ],
        [
            None,
            "Sivasaga\nr",
            "4",
            "3 (Nazira | 2), (Demow | 1)",
            None,
            None,
            None,
            "1 (Demow | 1)",
        ],
        [None, "Total", "4", "3", None, None, None, "1"],
        ["Inmates In\nRelief\nCamps", "District", "Total"],
        [None, "Sivasaga\nr", "80"],
        [None, "Total", "80"],
        ["Human\nLives Lost -\nConfirmed", "District", "Total"],
        [None, "Sivasaga\nr", "1"],
        [None, "Total", "1"],
        ["Animals\nAffected", "District", "Total"],
        [None, "Sivasaga\nr", ""],
    ]

    parsed = parse_extracted_tables(
        [[[row for row in table]]],
        report_heading="Assam Flood Report as on 25-07-2026",
    )

    assert parsed["report_date"] == "2026-07-25"
    assert {
        key: parsed["summary"][key]
        for key in {
            "affected_districts",
            "affected_revenue_circles",
            "affected_villages",
            "affected_population",
            "crop_area_submerged_hectares",
            "relief_camps_open",
            "relief_distribution_centres_open",
            "relief_camp_occupants",
            "confirmed_deaths",
        }
    } == {
        "affected_districts": 2,
        "affected_revenue_circles": 3,
        "affected_villages": 12,
        "affected_population": 125,
        "crop_area_submerged_hectares": 30.5,
        "relief_camps_open": 3,
        "relief_distribution_centres_open": 1,
        "relief_camp_occupants": 80,
        "confirmed_deaths": 1,
    }
    sivasagar = next(item for item in parsed["districts"] if item["district"] == "Sivasagar")
    assert sivasagar["affected_population"] == 100
    assert sivasagar["revenue_circles"] == ["Nazira", "Dimow"]


def test_affected_districts_survive_shifted_columns_and_split_header_rows() -> None:
    table = [
        ["District\nAffected", "No. of Districts", None, "Name of Affected Districts"],
        [None, "Affected", None, None],
        [None, "2", None, "Sivasagar, Charaideo"],
        ["No. Of\nRevenue\nCircles\nAffected", "3"],
        ["Name Of\nRevenue\nCircle\nAffected", "District", "Total", "Revenue Circle"],
        [None, "Sivasagar", "3", "Nazira, Demow, Sibsagar"],
        [None, "Total", "3", ""],
        ["Villages\nAffected", "District", "Total", "Revenue Circle"],
        [None, "Sivasagar", "12", ""],
        [None, "Total", "12", ""],
        [
            "Population\nAnd Crop\nArea\nSubmerged",
            "District",
            "Male",
            "Female",
            "Children",
            "Total",
            "Total Crop Area (in Hect.)",
        ],
        [None, "Sivasagar", "40", "40", "20", "100", "25.5"],
        [None, "Total", "50", "50", "25", "125", "30.5"],
        [
            "Relief\nCamps /\nCentres\nOpened",
            "District",
            "Total",
            "Relief Camp",
            None,
            None,
            None,
            "Relief Distribution Centres",
        ],
        [None, "Sivasagar", "4", "3", None, None, None, "1"],
        [None, "Total", "4", "3", None, None, None, "1"],
        ["Inmates In\nRelief\nCamps", "District", "Total"],
        [None, "Sivasagar", "80"],
        [None, "Total", "80"],
        ["Human\nLives Lost -\nConfirmed", "District", "Total"],
        [None, "Sivasagar", "1"],
        [None, "Total", "1"],
    ]

    parsed = parse_extracted_tables(
        [[table]],
        report_heading="Assam Flood Report as on 27-07-2026",
    )

    assert parsed["extractor_version"] == 7
    assert parsed["summary"]["affected_districts"] == 2
    assert parsed["affected_district_names"] == ["Sivasagar", "Charaideo"]


def test_circle_level_damage_is_preserved_and_aliases_are_normalised() -> None:
    table = [
        ["District\nAffected", "No. of", "Name of Affected Districts"],
        [None, "1", "Sivasagar"],
        ["No. Of\nRevenue\nCircles\nAffected", "2"],
        ["Name Of\nRevenue\nCircle\nAffected", "District", "Total", "Revenue Circle"],
        [None, "Sivasagar", "2", "Nazira, Sonari RC part"],
        [None, "Total", "2", ""],
        ["Villages\nAffected", "District", "Total", "Revenue Circle"],
        [None, "Sivasagar", "12", "(Nazira | 10), (Sonari RC part | 2)"],
        [None, "Total", "12", ""],
        [
            "Population\nAnd Crop\nArea\nSubmerged",
            "District",
            "Male",
            "Female",
            "Children",
            "Total",
            "Total Crop Area (in Hect.)",
            "Population and Crop Area Details",
        ],
        [
            None,
            "Sivasagar",
            "40",
            "40",
            "20",
            "100",
            "25.5",
            "(Nazira | Population Affected: 80 | Crop Area Submerged: 20.5), "
            "(Sonari RC part | Population Affected: 20 | Crop Area Submerged: 5)",
        ],
        [None, "Total", "40", "40", "20", "100", "25.5"],
        [
            "Relief\nCamps /\nCentres\nOpened",
            "District",
            "Total",
            "Relief Camp",
            None,
            None,
            None,
            "Relief Distribution Centres",
        ],
        [None, "Sivasagar", "3", "2 (Nazira | 2)", None, None, None, "1 (Sonari | 1)"],
        [None, "Total", "3", "2", None, None, None, "1"],
        ["Inmates In\nRelief\nCamps", "District", "Total", "Revenue Circlewise"],
        [None, "Sivasagar", "80", "(Nazira | 80), (Sonari RC part | 0)"],
        [None, "Total", "80"],
        ["Human\nLives Lost -\nConfirmed", "District", "Total", "Revenue Circlewise"],
        [None, "Sivasagar", "1", "1 (Nazira | 1), (Sonari RC part | 0)"],
        [None, "Total", "1"],
    ]

    parsed = parse_extracted_tables(
        [[table]],
        report_heading="Assam Flood Report as on 25-07-2026",
        circle_aliases={
            "nazira": "Nazira",
            "sonarircpart": "Sonari",
            "sonari": "Sonari",
        },
    )

    assert parsed["extractor_version"] == 7
    district = parsed["districts"][0]
    assert district["revenue_circles"] == ["Nazira", "Sonari"]
    assert district["revenue_circle_data"] == [
        {
            "affected_population": 80,
            "affected_villages": 10,
            "confirmed_deaths": 1,
            "crop_area_submerged_hectares": 20.5,
            "relief_camp_occupants": 80,
            "relief_camps_open": 2,
            "revenue_circle": "Nazira",
            "source_names": ["Nazira"],
        },
        {
            "affected_population": 20,
            "affected_villages": 2,
            "confirmed_deaths": 0,
            "crop_area_submerged_hectares": 5,
            "relief_camp_occupants": 0,
            "relief_distribution_centres_open": 1,
            "revenue_circle": "Sonari",
            "source_names": ["Sonari RC part", "Sonari"],
        },
    ]


def test_semantic_rows_survive_inserted_and_removed_spacer_columns() -> None:
    table = [
        ["District\nAffected", "No. of Districts", None, "Name of Affected Districts"],
        [None, None, "1", None, "Sivasagar"],
        ["No. Of\nRevenue\nCircles\nAffected", None, None, "1"],
        [
            "Name Of\nRevenue\nCircle\nAffected",
            None,
            "District",
            None,
            "Total",
            None,
            "Revenue Circle",
        ],
        [None, None, "Sivasagar", None, "1", None, "Nazira"],
        [None, None, "Total", None, "1"],
        ["Villages\nAffected", None, "District", None, "Total", None, "Revenue Circle"],
        [None, None, "Sivasagar", None, "2", None, "(Nazira | 2)"],
        [None, None, "Total", None, "2"],
        [
            "Population\nAnd Crop\nArea\nSubmerged",
            None,
            "District",
            None,
            "Male",
            None,
            "Female",
            "Children",
            None,
            "Total",
            "Total Crop Area (in Hect.)",
            "Population and Crop Area Details",
        ],
        [
            None,
            None,
            "Sivasagar",
            None,
            "40",
            None,
            "35",
            "25",
            None,
            "100",
            "4.5",
            "(Nazira | Population Affected: 100 | Crop Area Submerged: 4.5)",
        ],
        [None, None, "Total", "40", None, "35", "25", "100", "4.5"],
        [
            "Relief\nCamps /\nCentres\nOpened",
            None,
            "District",
            None,
            "Total",
            None,
            "Relief Camp",
            None,
            "Relief Distribution Centres",
        ],
        [
            None,
            None,
            "Sivasagar",
            None,
            "2",
            None,
            "1 (Nazira | 1)",
            None,
            "1 (Nazira | 1)",
        ],
        [None, None, "Total", None, "2", None, "1", None, "1"],
        ["Inmates In\nRelief\nCamps", None, "District", None, "Total", "Revenue Circlewise"],
        [None, None, "Sivasagar", None, "10", "(Nazira | 10)"],
        [None, None, "Total", None, "10"],
        ["Human\nLives Lost -\nConfirmed", None, "District", None, "Total", "Revenue Circlewise"],
        [None, None, "Sivasagar", None, "0", "0 (Nazira | 0)"],
        [None, None, "Total", None, "0"],
    ]

    parsed = parse_extracted_tables(
        [[table]],
        report_heading="Assam Flood Report as on 27-07-2026",
        circle_aliases={"nazira": "Nazira"},
    )

    assert parsed["summary"]["affected_population"] == 100
    assert parsed["summary"]["crop_area_submerged_hectares"] == 4.5
    assert parsed["summary"]["relief_camps_open"] == 1
    assert parsed["summary"]["relief_distribution_centres_open"] == 1
    assert parsed["districts"][0]["affected_population"] == 100
    assert parsed["districts"][0]["crop_area_submerged_hectares"] == 4.5


def test_real_2026_07_27_pdf_handles_page_layout_shift_and_split_detail() -> None:
    source = next(
        (
            Path(__file__).parents[1]
            / "data"
            / "raw"
            / "asdma"
            / "2026-07-27"
        ).glob("*.pdf")
    )

    parsed = parse_bulletin(source.read_bytes())

    assert parsed["extractor_version"] == 7
    assert parsed["rivers_above_danger_level"] == ["Dhansiri (S) (Numaligarh)"]
    assert parsed["rivers_above_highest_flood_level"] == []
    assert parsed["summary"]["affected_population"] == 445_495
    assert parsed["summary"]["crop_area_submerged_hectares"] == 37_139.52

    districts = {item["district"]: item for item in parsed["districts"]}
    assert districts["Charaideo"]["affected_population"] == 188_404
    assert districts["Charaideo"]["crop_area_submerged_hectares"] == 17_649
    assert districts["Sivasagar"]["affected_population"] == 144_461
    assert districts["Sivasagar"]["crop_area_submerged_hectares"] == 13_413.5

    nagaon_circles = {
        item["revenue_circle"]: item
        for item in districts["Nagaon"]["revenue_circle_data"]
    }
    assert nagaon_circles["Samaguri"]["crop_area_submerged_hectares"] == 123
    assert nagaon_circles["Kampur"]["crop_area_submerged_hectares"] == 196

    summary = parsed["summary"]
    assert summary["missing_people"] == 0
    assert summary["livestock_affected"] == {
        "total": 256_334,
        "big_animals": 69_225,
        "small_animals": 42_197,
        "poultry": 144_912,
    }
    assert summary["livestock_washed_away"] == {
        "total": 26_679,
        "big_animals": 270,
        "small_animals": 4_162,
        "poultry": 22_247,
    }
    assert summary["houses_damaged"] == {
        "fully_kutcha": 171,
        "fully_pucca": 5,
        "fully_total": 176,
        "partially_kutcha": 4_667,
        "partially_pucca": 98,
        "partially_total": 4_765,
    }
    assert summary["houses_damaged_others"] == {
        "other_huts": 21,
        "cattle_sheds": 285,
        "other_total": 306,
    }
    assert summary["rescue_operations"] == {
        "medical_teams_deployed": 179,
        "boats_deployed": 67,
        "people_evacuated_by_boat": 59,
        "animals_evacuated_by_boat": 36,
        "helicopters_deployed": 0,
        "people_evacuated_by_helicopter": 0,
    }
    assert summary["relief_distributed"] == {
        "rice_quintals": 1_191.092,
        "dal_quintals": 208.811,
        "salt_quintals": 49.7168,
        "mustard_oil_litres": 3_513.53,
        "green_fodder_quintals": 0,
        "wheat_bran_quintals": 7_620.39,
        "rice_bran_quintals": 53.03,
    }
    assert summary["infrastructure_incidents"]["road"] == 48
    assert summary["infrastructure_records_extracted"]["road"] == 48
    assert parsed["extraction_warnings"] == []
    assert parsed["relief_material_notes"]

    first_road = next(
        record
        for record in parsed["infrastructure"]
        if record["name"] == "Thukubill Satra Road"
    )
    assert first_road["district"] == "Charaideo"
    assert first_road["revenue_circle"] == "Sonari"
    assert first_road["match_scope"] == "coordinates"
    assert first_road["longitude"] == 95.032543
    assert first_road["latitude"] == 27.015787
    assert first_road["provenance"] == [
        {
            "page": 5,
            "table": 1,
            "row": 4,
            "section": "road",
        }
    ]
    assert parsed["field_provenance"]["summary.livestock_affected"][0]["page"] == 3
    assert parsed["field_provenance"]["summary.affected_population"][0]["page"] == 2


def test_real_2026_07_25_extracts_embankment_records_with_match_scope() -> None:
    source = next(
        (
            Path(__file__).parents[1]
            / "data"
            / "raw"
            / "asdma"
            / "2026-07-25"
        ).glob("*.pdf")
    )

    parsed = parse_bulletin(source.read_bytes())

    breached = [
        record
        for record in parsed["infrastructure"]
        if record["incident_type"] == "embankment_breached"
    ]
    affected = [
        record
        for record in parsed["infrastructure"]
        if record["incident_type"] == "embankment_affected"
    ]
    assert len(breached) == 10
    assert len(affected) == 7
    assert all(record["match_scope"] != "unresolved" for record in breached + affected)


def test_real_2026_07_26_preserves_reported_infrastructure_mismatch() -> None:
    source = next(
        (
            Path(__file__).parents[1]
            / "data"
            / "raw"
            / "asdma"
            / "2026-07-26"
        ).glob("*.pdf")
    )

    parsed = parse_bulletin(source.read_bytes())

    assert parsed["summary"]["infrastructure_incidents"]["road"] == 105
    assert parsed["summary"]["infrastructure_records_extracted"]["road"] == 97
    assert parsed["extraction_warnings"] == [
        {
            "code": "infrastructure_detail_count_mismatch",
            "incident_type": "road",
            "reported_count": 105,
            "extracted_record_count": 97,
        }
    ]


def test_extended_impact_fields_follow_reordered_semantic_headers() -> None:
    table = [
        [
            "Rescue\nOperation",
            "District",
            "Boats Deployed",
            "Medical Team Deployed",
            "Animal Evacuated By Boats",
            "Person Evacuated By Boats",
            "Person Evacuated By Helicopters",
            "Helicopters Deployed",
        ],
        [None, "Sivasagar", "67", "179", "36", "59", "0", "0"],
        [None, "Total", "67", "179", "36", "59", "0", "0"],
    ]

    parsed = extract_impact_sections(
        [[table]],
        known_districts={"Sivasagar"},
        circle_aliases={},
    )

    assert parsed["summary"]["rescue_operations"] == {
        "medical_teams_deployed": 179,
        "boats_deployed": 67,
        "people_evacuated_by_boat": 59,
        "animals_evacuated_by_boat": 36,
        "helicopters_deployed": 0,
        "people_evacuated_by_helicopter": 0,
    }


def test_extended_impact_rejects_unknown_semantic_columns() -> None:
    table = [
        [
            "Rescue\nOperation",
            "District",
            "Boats Deployed",
            "Unknown team count",
            "Person Evacuated By Boats",
            "Animal Evacuated By Boats",
            "Helicopters Deployed",
            "Person Evacuated By Helicopters",
        ],
        [None, "Total", "67", "179", "59", "36", "0", "0"],
    ]

    with pytest.raises(ImpactParseError, match="medical_teams_deployed"):
        extract_impact_sections(
            [[table]],
            known_districts={"Sivasagar"},
            circle_aliases={},
        )
