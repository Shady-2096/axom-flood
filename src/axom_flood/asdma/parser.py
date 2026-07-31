"""Strict extraction of public summary and district data from ASDMA PDFs."""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from io import BytesIO
from pathlib import Path
from typing import Any

import pdfplumber

from .impact import ImpactParseError, extract_impact_sections

SCHEMA_VERSION = 1
EXTRACTOR_VERSION = 7
DEFAULT_LOCALITY_REGISTRY = Path("config/assam-localities.json")
DEFAULT_DISTRICT_REGISTRY = Path("config/assam-districts.json")
_REPORT_DATE_RE = re.compile(r"Assam Flood Report as on (\d{2})-(\d{2})-(\d{4})")
_INTEGER_RE = re.compile(r"^\s*(\d+)")
_SCALAR_NUMBER_RE = re.compile(r"^\s*[\d,]+(?:\.\d+)?\s*$")
_CIRCLE_VALUE_RE = re.compile(r"\(([^|()]+?)\s*\|\s*([\d,.]+)\)", re.DOTALL)
_CIRCLE_POPULATION_RE = re.compile(
    r"\(([^|()]+?)\s*\|\s*Population\s+Affected:\s*([\d,]+)\s*\|\s*"
    r"Crop\s+Area\s+Submerged:\s*([\d,.]+)\)",
    re.IGNORECASE | re.DOTALL,
)

_SECTION_NAMES = {
    "Name Of Revenue Circle Affected": "revenue_circles",
    "Villages Affected": "villages",
    "Population And Crop Area Submerged": "population",
    "Relief Camps / Centres Opened": "camps",
    "Inmates In Relief Camps": "camp_inmates",
    "Human Lives Lost - Confirmed": "deaths",
}


class BulletinParseError(ValueError):
    """The PDF does not satisfy the expected ASDMA report contract."""


def _cell(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _label(value: Any) -> str:
    return " ".join(_cell(value).split())


def _district(value: Any) -> str:
    # PDF line wrapping often splits a single word: "Sivasaga\\nr".
    cleaned = _cell(value).replace("\n", "").strip()
    return re.sub(r"\s*\(([^)]+)\)", r" (\1)", cleaned)


def _integer(value: Any, *, field: str) -> int:
    match = _INTEGER_RE.match(_cell(value).replace(",", ""))
    if match is None:
        raise BulletinParseError(f"expected integer for {field}, got {_cell(value)!r}")
    return int(match.group(1))


def _number(value: Any, *, field: str) -> int | float:
    raw = _cell(value).replace(",", "")
    try:
        parsed = float(raw)
    except ValueError as exc:
        raise BulletinParseError(f"expected number for {field}, got {raw!r}") from exc
    return int(parsed) if parsed.is_integer() else parsed


def _row_value(row: Sequence[Any], index: int) -> Any:
    return row[index] if index < len(row) else None


def _scalar_numbers(
    row: Sequence[Any],
    *,
    after_index: int = 0,
) -> list[tuple[int, int | float]]:
    """Return standalone numeric cells, ignoring numbers embedded in detail text."""

    values: list[tuple[int, int | float]] = []
    for index in range(max(after_index + 1, 0), len(row)):
        raw = _cell(row[index])
        if _SCALAR_NUMBER_RE.fullmatch(raw):
            values.append((index, _number(raw, field=f"column {index}")))
    return values


def _semantic_district(
    row: Sequence[Any],
    known_districts: set[str],
) -> tuple[str, int] | None:
    """Find the district cell by meaning instead of assuming a physical column."""

    for index in range(1, len(row)):
        value = _label(row[index])
        if not value:
            continue
        if value == "District":
            return None
        if value == "Total":
            return "Total", index
        normalized = _district(row[index])
        if normalized in known_districts:
            return normalized, index
    return None


def _value_after_label(row: Sequence[Any], label: str) -> str | None:
    """Find the first non-empty cell after a semantic row label."""

    for index, value in enumerate(row):
        if _label(value) != label:
            continue
        for candidate in row[index + 1 :]:
            normalized = _label(candidate)
            if normalized:
                return normalized
    return None


def _first_scalar_number(
    row: Sequence[Any],
    *,
    after_index: int,
    field: str,
) -> int | float:
    values = _scalar_numbers(row, after_index=after_index)
    if not values:
        raise BulletinParseError(f"expected standalone number for {field}")
    return values[0][1]


def _population_circle_values_from_text(
    text: str,
) -> list[tuple[str, int, int | float]]:
    values: list[tuple[str, int, int | float]] = []
    for source_name, population, crop_area in _CIRCLE_POPULATION_RE.findall(text):
        values.append(
            (
                source_name.strip(),
                _integer(population, field=f"{source_name} affected_population"),
                _number(crop_area, field=f"{source_name} crop_area_submerged_hectares"),
            )
        )
    return values


def _population_detail_text(row: Sequence[Any]) -> str:
    return _bracket_text(row)


def _population_detail_complete(text: str) -> bool:
    if "Population Affected:" not in text:
        return False
    values = _population_circle_values_from_text(text)
    return (
        text.count("(") == text.count(")")
        and text.count("Population Affected:") == len(values)
    )


def _population_circle_values(
    row: Sequence[Any],
) -> list[tuple[str, int, int | float]]:
    text = _population_detail_text(row)
    if not _population_detail_complete(text):
        return []
    return _population_circle_values_from_text(text)


def _numbers_equal(left: int | float, right: int | float) -> bool:
    return abs(float(left) - float(right)) <= 1e-6


def _population_metrics(
    row: Sequence[Any],
    *,
    district_index: int,
    field: str,
) -> tuple[int, int | float]:
    """Resolve population and crop fields without relying on PDF cell positions.

    District rows are anchored by labelled revenue-circle detail when present.
    Total rows are identified by the demographic invariant
    male + female + children = total, followed by crop area. Blank spacer
    columns may appear or disappear without changing this semantic sequence.
    """

    numbers = [value for _, value in _scalar_numbers(row, after_index=district_index)]
    circle_values = _population_circle_values(row)
    if circle_values:
        population = sum(item[1] for item in circle_values)
        crop_area = sum(float(item[2]) for item in circle_values)
        matching_population = any(_numbers_equal(value, population) for value in numbers)
        matching_crop = any(_numbers_equal(value, crop_area) for value in numbers)
        if not matching_population or not matching_crop:
            raise BulletinParseError(
                f"{field} aggregate does not match its revenue-circle detail"
            )
        normalized_crop: int | float = int(crop_area) if crop_area.is_integer() else crop_area
        return population, normalized_crop

    for index in range(0, len(numbers) - 4):
        demographic_total = sum(float(value) for value in numbers[index : index + 3])
        declared_total = numbers[index + 3]
        if _numbers_equal(demographic_total, declared_total):
            return int(declared_total), numbers[index + 4]

    if len(numbers) == 2:
        population, crop_area = numbers
        return int(population), crop_area

    raise BulletinParseError(
        f"could not resolve {field} population and crop columns semantically"
    )


def _revenue_circle_names(
    row: Sequence[Any],
    *,
    district_index: int,
    aliases: dict[str, str],
) -> list[str]:
    for value in row[district_index + 1 :]:
        normalized = _cell(value)
        if (
            normalized
            and not _SCALAR_NUMBER_RE.fullmatch(normalized)
            and "|" not in normalized
        ):
            return [
                _circle_name(item.strip(), aliases)
                for item in normalized.split(",")
                if item.strip()
            ]
    return []


def _camp_metrics(
    row: Sequence[Any],
    *,
    district_index: int,
    field: str,
) -> tuple[int, int, list[tuple[str, int | float]], list[tuple[str, int | float]]]:
    """Resolve camp and distribution-centre columns from their detail grammar."""

    detail_cells: list[tuple[str, list[tuple[str, int | float]]]] = []
    for value in row[district_index + 1 :]:
        raw = _cell(value)
        circles = _circle_values([value], {})
        if circles:
            detail_cells.append((raw, circles))

    if len(detail_cells) >= 2:
        resolved: list[tuple[int, list[tuple[str, int | float]]]] = []
        for raw, circles in detail_cells[:2]:
            total = _integer(raw, field=field)
            circle_total = sum(float(value) for _, value in circles)
            if not _numbers_equal(total, circle_total):
                raise BulletinParseError(
                    f"{field} total {total} does not match circle detail {circle_total:g}"
                )
            resolved.append((total, circles))
        return resolved[0][0], resolved[1][0], resolved[0][1], resolved[1][1]

    numbers = [value for _, value in _scalar_numbers(row, after_index=district_index)]
    if len(numbers) >= 3:
        return int(numbers[-2]), int(numbers[-1]), [], []
    if len(numbers) == 2:
        return int(numbers[0]), int(numbers[1]), [], []
    raise BulletinParseError(f"could not resolve {field} camp columns semantically")


def _affected_district_summary(row: Sequence[Any]) -> tuple[int, list[str]] | None:
    """Read the count and names without depending on PDF merged-cell positions."""

    cells = [_label(value) for value in row]
    for index, value in enumerate(cells):
        if not value.isdigit():
            continue
        names_raw = next((cell for cell in cells[index + 1 :] if cell), "")
        if not names_raw:
            return None
        names = [name.strip() for name in names_raw.split(",") if name.strip()]
        count = int(value)
        if len(names) != count:
            raise BulletinParseError(
                "affected district count does not match extracted names: "
                f"declared {count}, extracted {len(names)}"
            )
        return count, names
    return None


def _section_for(first_cell: Any) -> str | None:
    normalized = _label(first_cell)
    for heading, section in _SECTION_NAMES.items():
        if normalized == heading:
            return section
    compact = re.sub(r"\s+", "", normalized).lower()
    if compact == "infrastructuredamaged-road":
        return "damaged_roads"
    if compact == "infrastructuredamaged-bridge":
        return "damaged_bridges"
    if compact == "infrastructuredamaged-embankmentbreached":
        return "breached_embankments"
    if compact == "infrastructuredamaged-embankmentaffected":
        return "affected_embankments"
    return None


def _district_record(records: dict[str, dict[str, Any]], district: str) -> dict[str, Any]:
    return records.setdefault("districts", {}).setdefault(district, {"district": district})


def _fold_place(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def load_circle_aliases(path: Path = DEFAULT_LOCALITY_REGISTRY) -> dict[str, str]:
    """Load reviewable source spellings from the Phase 1 locality registry."""

    if not path.exists():
        return {}
    import json

    document = json.loads(path.read_text())
    aliases: dict[str, str] = {}
    for locality in document.get("localities", []):
        canonical = locality["revenue_circle"]
        for spelling in [canonical, *locality.get("source_aliases", [])]:
            aliases[_fold_place(spelling)] = canonical
    return aliases


def load_district_names(path: Path = DEFAULT_DISTRICT_REGISTRY) -> set[str]:
    """Load canonical and source district names used to reject header fragments."""

    if not path.exists():
        return set()
    import json

    document = json.loads(path.read_text())
    names: set[str] = set()
    for district in document.get("districts", []):
        names.add(district["name"])
        names.update(district.get("source_aliases", []))
    return names


def _circle_name(value: str, aliases: dict[str, str]) -> str:
    source = " ".join(value.replace("\n", " ").split()).strip()
    return aliases.get(_fold_place(source), source)


def _circle_record(
    district: dict[str, Any],
    source_name: str,
    aliases: dict[str, str],
) -> dict[str, Any]:
    canonical = _circle_name(source_name, aliases)
    circles = district.setdefault("circle_data", {})
    record = circles.setdefault(
        canonical,
        {"revenue_circle": canonical, "source_names": []},
    )
    cleaned_source = " ".join(source_name.replace("\n", " ").split()).strip()
    if cleaned_source not in record["source_names"]:
        record["source_names"].append(cleaned_source)
    return record


def _bracket_text(row: Sequence[Any]) -> str:
    return " ".join(_cell(value).replace("\n", " ") for value in row if _cell(value))


def _circle_values(row: Sequence[Any], aliases: dict[str, str]) -> list[tuple[str, int | float]]:
    values: list[tuple[str, int | float]] = []
    for name, raw in _CIRCLE_VALUE_RE.findall(_bracket_text(row)):
        values.append((name.strip(), _number(raw, field=f"{name} circle value")))
    return values


def _apply_population_circle_values(
    record: dict[str, Any],
    text: str,
    aliases: dict[str, str],
) -> None:
    for source_name, population, crop_area in _population_circle_values_from_text(text):
        circle = _circle_record(record, source_name, aliases)
        circle["affected_population"] = population
        circle["crop_area_submerged_hectares"] = crop_area


def _validate_reconciliation(result: dict[str, Any]) -> None:
    """Reject column mistakes by reconciling every complete aggregate hierarchy."""

    affected_names = result.get("affected_district_names", [])
    districts = result["districts"]
    if result["summary"]["affected_districts"] != len(affected_names):
        raise BulletinParseError(
            "affected district total does not match the named affected districts"
        )

    fields = {
        "affected_revenue_circles",
        "affected_villages",
        "affected_population",
        "crop_area_submerged_hectares",
        "relief_camps_open",
        "relief_distribution_centres_open",
        "relief_camp_occupants",
        "confirmed_deaths",
    }
    district_names = set(districts)
    for field in fields:
        complete_affected_set = set(affected_names).issubset(district_names) and all(
            field in districts[name] for name in affected_names
        )
        populated_records = [record for record in districts.values() if field in record]
        if complete_affected_set and populated_records:
            district_total = sum(float(record[field]) for record in populated_records)
            if not _numbers_equal(result["summary"][field], district_total):
                raise BulletinParseError(
                    f"{field} state total {result['summary'][field]} does not match "
                    f"district total {district_total:g}"
                )

        for district, record in districts.items():
            circle_records = list(record.get("circle_data", {}).values())
            if (
                field not in record
                or not circle_records
                or not all(field in circle for circle in circle_records)
            ):
                continue
            circle_total = sum(float(circle[field]) for circle in circle_records)
            if not _numbers_equal(record[field], circle_total):
                raise BulletinParseError(
                    f"{district} {field} total {record[field]} does not match "
                    f"revenue-circle total {circle_total:g}"
                )


def parse_extracted_tables(
    pages: Iterable[list[list[Any]]],
    *,
    report_heading: str,
    circle_aliases: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Parse pdfplumber table rows. Exposed separately for deterministic fixture tests."""

    page_list = list(pages)
    circle_aliases = circle_aliases if circle_aliases is not None else load_circle_aliases()
    date_match = _REPORT_DATE_RE.search(report_heading)
    if date_match is None:
        raise BulletinParseError("could not find report date inside PDF")
    day, month, year = date_match.groups()

    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "extractor_version": EXTRACTOR_VERSION,
        "report_date": f"{year}-{month}-{day}",
        "rivers_above_danger_level": [],
        "rivers_above_highest_flood_level": [],
        "summary": {},
        "districts": {},
    }
    section: str | None = None
    waiting_for_affected_districts = False
    known_districts = load_district_names()
    pending_population: tuple[dict[str, Any], str, str, list[dict[str, Any]]] | None = None
    field_provenance: dict[str, list[dict[str, Any]]] = {}

    for page_number, tables in enumerate(page_list, start=1):
        for table_number, table in enumerate(tables, start=1):
            for row_number, row in enumerate(table, start=1):
                if not row:
                    continue
                first = _label(_row_value(row, 0))
                row_section = _section_for(_row_value(row, 0))
                source_ref = {
                    "page": page_number,
                    "table": table_number,
                    "row": row_number,
                    "section": row_section or section or "report_summary",
                }
                # A non-empty first column marks a new report section. Unknown
                # sections must clear state so their district-shaped rows are
                # never misread using the preceding known section's schema.
                if first:
                    section = row_section

                danger_value = _value_after_label(row, "Rivers flowing above danger level")
                if danger_value is not None:
                    value = danger_value
                    result["rivers_above_danger_level"] = (
                        []
                        if value == "Nil"
                        else [item.strip() for item in value.split(",") if item.strip()]
                    )
                    field_provenance["rivers_above_danger_level"] = [source_ref]
                highest_value = _value_after_label(
                    row, "Rivers flowing above highest flood level"
                )
                if highest_value is not None:
                    value = highest_value
                    result["rivers_above_highest_flood_level"] = (
                        []
                        if value == "Nil"
                        else [item.strip() for item in value.split(",") if item.strip()]
                    )
                    field_provenance["rivers_above_highest_flood_level"] = [source_ref]

                if first == "District Affected":
                    waiting_for_affected_districts = True
                    continue
                if waiting_for_affected_districts:
                    affected = _affected_district_summary(row)
                    if affected is not None:
                        count, names = affected
                        result["summary"]["affected_districts"] = count
                        result["affected_district_names"] = names
                        field_provenance["summary.affected_districts"] = [source_ref]
                        field_provenance["affected_district_names"] = [source_ref]
                        known_districts.update(names)
                        waiting_for_affected_districts = False

                if first == "No. Of Revenue Circles Affected":
                    result["summary"]["affected_revenue_circles"] = int(
                        _first_scalar_number(
                            row,
                            after_index=0,
                            field="affected_revenue_circles",
                        )
                    )
                    field_provenance["summary.affected_revenue_circles"] = [source_ref]
                    continue

                district_cell = _semantic_district(row, known_districts)
                if district_cell is None:
                    if section == "population" and pending_population is not None:
                        pending_record, pending_text, pending_district, pending_refs = (
                            pending_population
                        )
                        continuation = _population_detail_text(row)
                        if continuation:
                            combined = f"{pending_text} {continuation}"
                            combined_refs = [*pending_refs, source_ref]
                            if _population_detail_complete(combined):
                                _apply_population_circle_values(
                                    pending_record,
                                    combined,
                                    circle_aliases,
                                )
                                for source_name, _, _ in _population_circle_values_from_text(
                                    combined
                                ):
                                    circle = _circle_name(source_name, circle_aliases)
                                    for field in (
                                        "affected_population",
                                        "crop_area_submerged_hectares",
                                    ):
                                        field_provenance[
                                            f"districts[{pending_district}]."
                                            f"revenue_circles[{circle}].{field}"
                                        ] = combined_refs
                                pending_population = None
                            else:
                                pending_population = (
                                    pending_record,
                                    combined,
                                    pending_district,
                                    combined_refs,
                                )
                    continue
                if pending_population is not None:
                    raise BulletinParseError(
                        "population revenue-circle detail was interrupted by a new row"
                    )
                district, district_index = district_cell

                if section == "revenue_circles":
                    if district == "Total":
                        result["summary"]["affected_revenue_circles"] = int(
                            _first_scalar_number(
                                row,
                                after_index=district_index,
                                field="affected_revenue_circles total",
                            )
                        )
                        field_provenance["summary.affected_revenue_circles"] = [source_ref]
                    else:
                        record = _district_record(result, district)
                        record["affected_revenue_circles"] = int(
                            _first_scalar_number(
                                row,
                                after_index=district_index,
                                field=f"{district} affected_revenue_circles",
                            )
                        )
                        record["revenue_circles"] = _revenue_circle_names(
                            row,
                            district_index=district_index,
                            aliases=circle_aliases,
                        )
                        field_provenance[
                            f"districts[{district}].affected_revenue_circles"
                        ] = [source_ref]
                        field_provenance[f"districts[{district}].revenue_circles"] = [
                            source_ref
                        ]
                elif section == "villages":
                    if district == "Total":
                        result["summary"]["affected_villages"] = int(
                            _first_scalar_number(
                                row,
                                after_index=district_index,
                                field="affected_villages total",
                            )
                        )
                        field_provenance["summary.affected_villages"] = [source_ref]
                    else:
                        record = _district_record(result, district)
                        record["affected_villages"] = int(
                            _first_scalar_number(
                                row,
                                after_index=district_index,
                                field=f"{district} affected_villages",
                            )
                        )
                        for source_name, value in _circle_values(row, circle_aliases):
                            circle = _circle_record(record, source_name, circle_aliases)
                            circle["affected_villages"] = int(value)
                            field_provenance[
                                f"districts[{district}].revenue_circles"
                                f"[{circle['revenue_circle']}].affected_villages"
                            ] = [source_ref]
                        field_provenance[f"districts[{district}].affected_villages"] = [
                            source_ref
                        ]
                elif section == "population":
                    population, crop_area = _population_metrics(
                        row,
                        district_index=district_index,
                        field=f"{district} population",
                    )
                    if district == "Total":
                        result["summary"]["affected_population"] = population
                        result["summary"]["crop_area_submerged_hectares"] = crop_area
                        field_provenance["summary.affected_population"] = [source_ref]
                        field_provenance[
                            "summary.crop_area_submerged_hectares"
                        ] = [source_ref]
                    else:
                        record = _district_record(result, district)
                        record["affected_population"] = population
                        record["crop_area_submerged_hectares"] = crop_area
                        detail_text = _population_detail_text(row)
                        if _population_detail_complete(detail_text):
                            _apply_population_circle_values(
                                record,
                                detail_text,
                                circle_aliases,
                            )
                            for source_name, _, _ in _population_circle_values_from_text(
                                detail_text
                            ):
                                circle = _circle_name(source_name, circle_aliases)
                                for field in (
                                    "affected_population",
                                    "crop_area_submerged_hectares",
                                ):
                                    field_provenance[
                                        f"districts[{district}].revenue_circles"
                                        f"[{circle}].{field}"
                                    ] = [source_ref]
                        elif "Population Affected:" in detail_text:
                            pending_population = (
                                record,
                                detail_text,
                                district,
                                [source_ref],
                            )
                        field_provenance[
                            f"districts[{district}].affected_population"
                        ] = [source_ref]
                        field_provenance[
                            f"districts[{district}].crop_area_submerged_hectares"
                        ] = [source_ref]
                elif section == "camps":
                    camps, centres, camp_circles, centre_circles = _camp_metrics(
                        row,
                        district_index=district_index,
                        field=f"{district} relief centres",
                    )
                    if district == "Total":
                        result["summary"]["relief_camps_open"] = camps
                        result["summary"]["relief_distribution_centres_open"] = centres
                        field_provenance["summary.relief_camps_open"] = [source_ref]
                        field_provenance[
                            "summary.relief_distribution_centres_open"
                        ] = [source_ref]
                    else:
                        record = _district_record(result, district)
                        record["relief_camps_open"] = camps
                        record["relief_distribution_centres_open"] = centres
                        for source_name, value in camp_circles:
                            circle = _circle_record(record, source_name, circle_aliases)
                            circle["relief_camps_open"] = int(value)
                            field_provenance[
                                f"districts[{district}].revenue_circles"
                                f"[{circle['revenue_circle']}].relief_camps_open"
                            ] = [source_ref]
                        for source_name, value in centre_circles:
                            circle = _circle_record(record, source_name, circle_aliases)
                            circle["relief_distribution_centres_open"] = int(value)
                            field_provenance[
                                f"districts[{district}].revenue_circles"
                                f"[{circle['revenue_circle']}]."
                                "relief_distribution_centres_open"
                            ] = [source_ref]
                        field_provenance[f"districts[{district}].relief_camps_open"] = [
                            source_ref
                        ]
                        field_provenance[
                            f"districts[{district}].relief_distribution_centres_open"
                        ] = [source_ref]
                elif section == "camp_inmates":
                    occupants = int(
                        _first_scalar_number(
                            row,
                            after_index=district_index,
                            field=f"{district} relief_camp_occupants",
                        )
                    )
                    if district == "Total":
                        result["summary"]["relief_camp_occupants"] = occupants
                        field_provenance["summary.relief_camp_occupants"] = [source_ref]
                    else:
                        record = _district_record(result, district)
                        record["relief_camp_occupants"] = occupants
                        for source_name, value in _circle_values(row, circle_aliases):
                            circle = _circle_record(record, source_name, circle_aliases)
                            circle["relief_camp_occupants"] = int(value)
                            field_provenance[
                                f"districts[{district}].revenue_circles"
                                f"[{circle['revenue_circle']}].relief_camp_occupants"
                            ] = [source_ref]
                        field_provenance[
                            f"districts[{district}].relief_camp_occupants"
                        ] = [source_ref]
                elif section == "deaths":
                    deaths = int(
                        _first_scalar_number(
                            row,
                            after_index=district_index,
                            field=f"{district} confirmed_deaths",
                        )
                    )
                    if district == "Total":
                        result["summary"]["confirmed_deaths"] = deaths
                        field_provenance["summary.confirmed_deaths"] = [source_ref]
                    else:
                        record = _district_record(result, district)
                        record["confirmed_deaths"] = deaths
                        for source_name, value in _circle_values(row, circle_aliases):
                            circle = _circle_record(record, source_name, circle_aliases)
                            circle["confirmed_deaths"] = int(value)
                            field_provenance[
                                f"districts[{district}].revenue_circles"
                                f"[{circle['revenue_circle']}].confirmed_deaths"
                            ] = [source_ref]
                        field_provenance[f"districts[{district}].confirmed_deaths"] = [
                            source_ref
                        ]
                elif section in {
                    "damaged_roads",
                    "damaged_bridges",
                    "breached_embankments",
                    "affected_embankments",
                }:
                    field = {
                        "damaged_roads": "damaged_roads",
                        "damaged_bridges": "damaged_bridges",
                        "breached_embankments": "breached_embankments",
                        "affected_embankments": "affected_embankments",
                    }[section]
                    if district == "Total":
                        result["summary"][field] = int(
                            _first_scalar_number(
                                row,
                                after_index=district_index,
                                field=f"{field} total",
                            )
                        )
                        field_provenance[f"summary.{field}"] = [source_ref]

    if pending_population is not None:
        raise BulletinParseError("population revenue-circle detail ended mid-record")

    required = {
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
    missing = sorted(required - result["summary"].keys())
    if missing:
        raise BulletinParseError(f"required report totals were not extracted: {', '.join(missing)}")

    _validate_reconciliation(result)

    try:
        impact = extract_impact_sections(
            page_list,
            known_districts=known_districts,
            circle_aliases=circle_aliases,
        )
    except ImpactParseError as exc:
        raise BulletinParseError(str(exc)) from exc
    result["summary"].update(impact["summary"])
    for district, values in impact["districts"].items():
        _district_record(result, district).update(
            {key: value for key, value in values.items() if key != "district"}
        )
    field_provenance.update(impact["field_provenance"])
    result["field_provenance"] = field_provenance
    result["relief_material_notes"] = impact["relief_material_notes"]
    result["infrastructure"] = impact["infrastructure"]
    result["extraction_warnings"] = impact["extraction_warnings"]

    for district in result["districts"].values():
        circle_data = district.pop("circle_data", {})
        district["revenue_circle_data"] = sorted(
            circle_data.values(), key=lambda item: item["revenue_circle"]
        )
    result["districts"] = sorted(result["districts"].values(), key=lambda item: item["district"])
    return result


def parse_bulletin(
    content: bytes,
    *,
    circle_aliases: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Extract and validate a complete ASDMA bulletin from PDF bytes."""

    if not content.startswith(b"%PDF"):
        raise BulletinParseError("input is not a PDF")

    try:
        with pdfplumber.open(BytesIO(content)) as pdf:
            if not pdf.pages:
                raise BulletinParseError("PDF contains no pages")
            first_page_text = pdf.pages[0].extract_text() or ""
            pages = [[table for table in page.extract_tables() if table] for page in pdf.pages]
    except BulletinParseError:
        raise
    except Exception as exc:
        raise BulletinParseError(f"could not read PDF: {exc}") from exc

    return parse_extracted_tables(
        pages,
        report_heading=first_page_text,
        circle_aliases=circle_aliases,
    )
