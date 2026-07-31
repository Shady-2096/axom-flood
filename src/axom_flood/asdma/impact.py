"""Semantic extraction of the extended ASDMA impact sections.

This module deliberately works from section labels and normalized value
sequences.  Physical PDF columns are not stable between report revisions.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from typing import Any

_NUMBER_CELL_RE = re.compile(r"^[\d,\s]+(?:\.\d[\d\s]*)?$")
_CIRCLE_COUNT_RE = re.compile(r"\(([^|()]+?)\s*\|\s*([\d,.]+)\)", re.DOTALL)

_SECTION_LABELS = {
    "humanliveslost-missing": "missing_people",
    "animalsaffected": "livestock_affected",
    "animalswashedaway": "livestock_washed_away",
    "housesdamaged": "houses_damaged",
    "housesdamagedothers": "houses_damaged_others",
    "rescueoperation": "rescue_operations",
    "reliefdistributed": "relief_distributed",
    "reliefdistributed-others": "relief_distributed_others",
    "infrastructuredamaged-road": "road",
    "infrastructuredamaged-bridge": "bridge",
    "infrastructuredamaged-embankmentbreached": "embankment_breached",
    "infrastructuredamaged-embankmentaffected": "embankment_affected",
}

_INFRASTRUCTURE_SECTIONS = {
    "road",
    "bridge",
    "embankment_breached",
    "embankment_affected",
}

_SECTION_FIELDS = {
    "missing_people": ("total",),
    "livestock_affected": ("total", "big_animals", "small_animals", "poultry"),
    "livestock_washed_away": ("total", "big_animals", "small_animals", "poultry"),
    "houses_damaged": (
        "fully_kutcha",
        "fully_pucca",
        "fully_total",
        "partially_kutcha",
        "partially_pucca",
        "partially_total",
    ),
    "houses_damaged_others": ("other_huts", "cattle_sheds", "other_total"),
    "rescue_operations": (
        "medical_teams_deployed",
        "boats_deployed",
        "people_evacuated_by_boat",
        "animals_evacuated_by_boat",
        "helicopters_deployed",
        "people_evacuated_by_helicopter",
    ),
    "relief_distributed": (
        "rice_quintals",
        "dal_quintals",
        "salt_quintals",
        "mustard_oil_litres",
        "green_fodder_quintals",
        "wheat_bran_quintals",
        "rice_bran_quintals",
    ),
}

_SECTION_FIELD_ALIASES = {
    "total": ("total",),
    "big_animals": ("big",),
    "small_animals": ("small",),
    "poultry": ("poultry",),
    "fully_kutcha": ("fullyseverelykutcha", "fullyseverelykuccha"),
    "fully_pucca": ("fullyseverelypucca", "fullyseverelypukka"),
    "fully_total": ("fullyseverelytotal",),
    "partially_kutcha": ("partiallykutcha", "partiallykuccha"),
    "partially_pucca": ("partiallypucca", "partiallypukka"),
    "partially_total": ("partiallytotal",),
    "other_huts": ("othershuts",),
    "cattle_sheds": ("otherscattleshed", "othercattleshed"),
    "other_total": ("otherstotal",),
    "medical_teams_deployed": ("medicalteamdeployed",),
    "boats_deployed": ("boatsdeployed",),
    "people_evacuated_by_boat": ("personevacuatedbyboats",),
    "animals_evacuated_by_boat": ("animalevacuatedbyboats",),
    "helicopters_deployed": ("helicoptersdeployed",),
    "people_evacuated_by_helicopter": ("personevacuatedbyhelicopters",),
    "rice_quintals": ("riceinq",),
    "dal_quintals": ("dalinq",),
    "salt_quintals": ("saltinq",),
    "mustard_oil_litres": ("moil(inl)", "moilinl", "mustardoilinl"),
    "green_fodder_quintals": (
        "cattlefeedgreenfooderinq",
        "cattlefeedgreenfodderinq",
    ),
    "wheat_bran_quintals": ("cattlefeedwheatbraninq",),
    "rice_bran_quintals": ("cattlefeedricebraninq",),
}


class ImpactParseError(ValueError):
    """An extended impact section does not satisfy its arithmetic contract."""


def _cell(value: Any) -> str:
    return " ".join(("" if value is None else str(value)).replace("\n", " ").split())


def _compact(value: Any) -> str:
    return re.sub(r"\s+", "", _cell(value)).casefold()


def _number(value: Any, *, field: str) -> int | float:
    raw = _cell(value)
    if not raw or not _NUMBER_CELL_RE.fullmatch(raw):
        raise ImpactParseError(f"expected number for {field}, got {raw!r}")
    parsed = float(raw.replace(",", "").replace(" ", ""))
    return int(parsed) if parsed.is_integer() else parsed


def _numbers_after(row: Sequence[Any], index: int) -> list[int | float]:
    values: list[int | float] = []
    for cell in row[index + 1 :]:
        raw = _cell(cell)
        if raw and _NUMBER_CELL_RE.fullmatch(raw):
            values.append(_number(raw, field="impact value"))
    return values


def _semantic_header_map(
    section: str,
    header_rows: Sequence[Sequence[Any]],
) -> dict[str, int]:
    """Resolve logical fields from possibly split ASDMA header rows."""

    width = max((len(row) for row in header_rows), default=0)
    labels = [
        re.sub(
            r"[^a-z0-9]",
            "",
            "".join(
                _compact(row[index])
                for row in header_rows
                if index < len(row) and _cell(row[index])
            ),
        )
        for index in range(width)
    ]
    result: dict[str, int] = {}
    for field in _SECTION_FIELDS[section]:
        aliases = _SECTION_FIELD_ALIASES[field]
        matches = [
            index
            for index, label in enumerate(labels)
            if any(alias in label for alias in aliases)
        ]
        if len(matches) != 1:
            raise ImpactParseError(
                f"{section} header must resolve {field} exactly once; "
                f"found {len(matches)} matches"
            )
        result[field] = matches[0]
    return result


def _semantic_values(
    row: Sequence[Any],
    section: str,
    indices: dict[str, int],
) -> list[int | float]:
    # PDF page breaks can remove spacer columns without repeating the header.
    # Preserve the semantic order learned from the header, then consume the
    # numeric cells in that order. A reordered header therefore reorders the
    # field mapping, while inserted or removed blank cells remain harmless.
    ordered_fields = [
        field for field, _ in sorted(indices.items(), key=lambda item: item[1])
    ]
    numeric_values = [
        _number(value, field=f"{section} value")
        for value in row
        if _cell(value) and _NUMBER_CELL_RE.fullmatch(_cell(value))
    ]
    if section == "missing_people":
        if not numeric_values:
            raise ImpactParseError("missing_people requires a total")
        return [numeric_values[0]]
    if len(numeric_values) != len(ordered_fields):
        raise ImpactParseError(
            f"{section} requires exactly {len(ordered_fields)} semantic values, "
            f"found {len(numeric_values)}"
        )
    by_field = dict(zip(ordered_fields, numeric_values, strict=True))
    return [by_field[field] for field in _SECTION_FIELDS[section]]


def _source_ref(
    *,
    page: int,
    table: int,
    row: int,
    section: str,
) -> dict[str, Any]:
    return {
        "page": page,
        "table": table,
        "row": row,
        "section": section,
    }


def _district_cell(
    row: Sequence[Any],
    known_districts: set[str],
) -> tuple[str, int] | None:
    for index, value in enumerate(row[1:], start=1):
        raw = _cell(value).replace(" ", "")
        if raw == "Total":
            return "Total", index
        for district in known_districts:
            if raw == district.replace(" ", ""):
                return district, index
    return None


def _district_at_index(
    row: Sequence[Any],
    index: int,
    known_districts: set[str],
) -> tuple[str, int] | None:
    if index >= len(row):
        return None
    raw = _cell(row[index]).replace(" ", "")
    if raw == "Total":
        return "Total", index
    for district in known_districts:
        if raw == district.replace(" ", ""):
            return district, index
    return None


def _assert_total(parts: Sequence[int | float], total: int | float, field: str) -> None:
    if abs(sum(float(value) for value in parts) - float(total)) > 1e-6:
        raise ImpactParseError(f"{field} total does not match its component values")


def _breakdown(
    values: Sequence[int | float],
    names: Sequence[str],
    *,
    field: str,
) -> dict[str, int | float]:
    if len(values) < len(names):
        raise ImpactParseError(
            f"{field} requires {len(names)} values, found {len(values)}"
        )
    result = dict(zip(names, values, strict=True))
    if names == ("total", "big_animals", "small_animals", "poultry"):
        _assert_total(values[1:4], values[0], field)
    elif names == (
        "fully_kutcha",
        "fully_pucca",
        "fully_total",
        "partially_kutcha",
        "partially_pucca",
        "partially_total",
    ):
        _assert_total(values[0:2], values[2], f"{field} fully")
        _assert_total(values[3:5], values[5], f"{field} partially")
    elif names == ("other_huts", "cattle_sheds", "other_total"):
        _assert_total(values[0:2], values[2], field)
    return result


def _impact_field(
    section: str,
    values: Sequence[int | float],
) -> int | float | dict[str, int | float]:
    if section == "missing_people":
        if not values:
            raise ImpactParseError("missing_people requires a total")
        return values[0]
    if section in {"livestock_affected", "livestock_washed_away"}:
        return _breakdown(
            values[:4],
            ("total", "big_animals", "small_animals", "poultry"),
            field=section,
        )
    if section == "houses_damaged":
        return _breakdown(
            values[:6],
            (
                "fully_kutcha",
                "fully_pucca",
                "fully_total",
                "partially_kutcha",
                "partially_pucca",
                "partially_total",
            ),
            field=section,
        )
    if section == "houses_damaged_others":
        return _breakdown(
            values[:3],
            ("other_huts", "cattle_sheds", "other_total"),
            field=section,
        )
    if section == "rescue_operations":
        return _breakdown(
            values[:6],
            (
                "medical_teams_deployed",
                "boats_deployed",
                "people_evacuated_by_boat",
                "animals_evacuated_by_boat",
                "helicopters_deployed",
                "people_evacuated_by_helicopter",
            ),
            field=section,
        )
    if section == "relief_distributed":
        return _breakdown(
            values[:7],
            (
                "rice_quintals",
                "dal_quintals",
                "salt_quintals",
                "mustard_oil_litres",
                "green_fodder_quintals",
                "wheat_bran_quintals",
                "rice_bran_quintals",
            ),
            field=section,
        )
    raise ImpactParseError(f"unsupported impact section {section}")


def _header_index(row: Sequence[Any], starts_with: str) -> int | None:
    target = starts_with.casefold()
    for index, value in enumerate(row):
        if _compact(value).startswith(target):
            return index
    return None


def _infra_header_map(row: Sequence[Any]) -> dict[str, int]:
    fields = {
        "district": _header_index(row, "district"),
        "number": _header_index(row, "number"),
        "revenue_circle": _header_index(row, "revenue"),
        "department": _header_index(row, "departme"),
        "village": _header_index(row, "village"),
        "location": _header_index(row, "location"),
        "longitude": _header_index(row, "longitud"),
        "latitude": _header_index(row, "latitude"),
        "remarks": _header_index(row, "remarks"),
    }
    missing = [key for key, index in fields.items() if index is None]
    if missing:
        raise ImpactParseError(
            "infrastructure header lacks semantic columns: " + ", ".join(missing)
        )
    revenue_index = int(fields["revenue_circle"])
    department_index = int(fields["department"])
    name_index = next(
        (
            index
            for index in range(revenue_index + 1, department_index)
            if _cell(row[index])
        ),
        revenue_index + 1,
    )
    return {key: int(value) for key, value in fields.items()} | {"name": name_index}


def _coordinate(raw: str, *, kind: str) -> tuple[float | None, str]:
    if not raw:
        return None, "missing"
    try:
        value = float(raw.replace(" ", ""))
    except ValueError:
        return None, "invalid"
    valid = 89.5 <= value <= 97.5 if kind == "longitude" else 24 <= value <= 29.5
    return (value, "valid") if valid else (None, "invalid")


def _circle_from_cell(
    value: Any,
    aliases: dict[str, str],
) -> str | None:
    match = _CIRCLE_COUNT_RE.search(_cell(value))
    if match is None:
        return None
    source = _cell(match.group(1))
    folded = re.sub(r"[^a-z0-9]", "", source.casefold())
    return aliases.get(folded, source)


def _append_continuation(
    record: dict[str, Any],
    row: Sequence[Any],
    indices: dict[str, int],
    source_ref: dict[str, Any],
) -> None:
    for source_field, target_field in (
        ("name", "name"),
        ("department", "department"),
        ("village", "village"),
        ("location", "source_location_text"),
        ("remarks", "remarks"),
    ):
        value = (
            _cell(row[indices[source_field]])
            if indices[source_field] < len(row)
            else ""
        )
        if value:
            existing = record.get(target_field, "") or ""
            record[target_field] = f"{existing} {value}".strip()
    record["provenance"].append(source_ref)


def _infrastructure_record(
    *,
    row: Sequence[Any],
    indices: dict[str, int],
    incident_type: str,
    district: str | None,
    revenue_circle: str | None,
    source_ref: dict[str, Any],
) -> dict[str, Any] | None:
    def value(field: str) -> str:
        index = indices[field]
        return _cell(row[index]) if index < len(row) else ""

    name = value("name")
    if not name or name.casefold() in {"nil", "name"}:
        return None
    longitude_raw = value("longitude")
    latitude_raw = value("latitude")
    longitude, longitude_state = _coordinate(longitude_raw, kind="longitude")
    latitude, latitude_state = _coordinate(latitude_raw, kind="latitude")
    coordinate_validation = (
        "valid"
        if longitude_state == latitude_state == "valid"
        else "missing"
        if longitude_state == latitude_state == "missing"
        else "invalid"
    )
    match_scope = (
        "coordinates"
        if coordinate_validation == "valid"
        else "revenue_circle"
        if revenue_circle
        else "district"
        if district
        else "unresolved"
    )
    return {
        "incident_type": incident_type,
        "district": district,
        "revenue_circle": revenue_circle,
        "name": name,
        "department": value("department") or None,
        "village": value("village") or None,
        "source_location_text": value("location") or None,
        "longitude": longitude,
        "latitude": latitude,
        "longitude_source_text": longitude_raw or None,
        "latitude_source_text": latitude_raw or None,
        "coordinate_validation": coordinate_validation,
        "remarks": value("remarks") or None,
        "match_scope": match_scope,
        "provenance": [source_ref],
    }


def extract_impact_sections(
    pages: Iterable[list[list[Any]]],
    *,
    known_districts: set[str],
    circle_aliases: dict[str, str],
) -> dict[str, Any]:
    """Extract Phase B aggregates, raw relief notes, and infrastructure records."""

    summary: dict[str, Any] = {}
    districts: dict[str, dict[str, Any]] = {}
    field_provenance: dict[str, list[dict[str, Any]]] = {}
    relief_material_notes: list[dict[str, Any]] = []
    infrastructure: list[dict[str, Any]] = []
    declared_infrastructure: dict[str, int] = {}
    declared_infrastructure_provenance: dict[str, dict[str, Any]] = {}
    extraction_warnings: list[dict[str, Any]] = []

    section: str | None = None
    section_header_rows: list[Sequence[Any]] = []
    section_indices: dict[str, int] | None = None
    section_district_index: int | None = None
    infrastructure_indices: dict[str, int] | None = None
    current_district: str | None = None
    current_circle: str | None = None
    last_infrastructure: dict[str, Any] | None = None

    for page_number, tables in enumerate(pages, start=1):
        for table_number, table in enumerate(tables, start=1):
            for row_number, row in enumerate(table, start=1):
                if not row:
                    continue
                compact_first = _compact(row[0])
                row_section = _SECTION_LABELS.get(compact_first)
                compact_row = [_compact(value) for value in row]
                if (
                    row_section is None
                    and "district" in compact_row
                    and "babyfoodliquid" in compact_row
                    and "babyfoodsolid" in compact_row
                ):
                    row_section = "relief_distributed_others"
                if row_section is not None:
                    section = row_section
                    section_header_rows = [row]
                    section_indices = None
                    section_district_index = _header_index(row, "district")
                    current_district = None
                    current_circle = None
                    last_infrastructure = None
                    infrastructure_indices = (
                        _infra_header_map(row)
                        if row_section in _INFRASTRUCTURE_SECTIONS
                        else None
                    )
                    continue
                if _cell(row[0]):
                    section = None
                    section_header_rows = []
                    section_indices = None
                    section_district_index = None
                    infrastructure_indices = None
                    continue
                if section is None:
                    continue

                source_ref = _source_ref(
                    page=page_number,
                    table=table_number,
                    row=row_number,
                    section=section,
                )
                district_cell = (
                    _district_cell(row, known_districts)
                    if section in _INFRASTRUCTURE_SECTIONS
                    else _district_at_index(
                        row,
                        section_district_index,
                        known_districts,
                    )
                    if section_district_index is not None
                    else None
                )

                if section in _INFRASTRUCTURE_SECTIONS:
                    assert infrastructure_indices is not None
                    district_raw = _cell(row[infrastructure_indices["district"]])
                    if district_raw.replace(" ", "") == "Total":
                        number_raw = _cell(row[infrastructure_indices["number"]])
                        if number_raw:
                            declared_infrastructure[section] = int(
                                _number(number_raw, field=f"{section} total")
                            )
                            declared_infrastructure_provenance[section] = source_ref
                        current_district = None
                        current_circle = None
                        last_infrastructure = None
                        continue
                    if district_cell is not None and district_cell[0] != "Total":
                        current_district = district_cell[0]
                    circle_value = row[infrastructure_indices["revenue_circle"]]
                    parsed_circle = _circle_from_cell(circle_value, circle_aliases)
                    if parsed_circle is not None:
                        current_circle = parsed_circle
                    record = _infrastructure_record(
                        row=row,
                        indices=infrastructure_indices,
                        incident_type=section,
                        district=current_district,
                        revenue_circle=current_circle,
                        source_ref=source_ref,
                    )
                    if record is not None:
                        infrastructure.append(record)
                        last_infrastructure = record
                    elif (
                        last_infrastructure is not None
                        and not district_raw
                        and not _cell(circle_value)
                        and any(_cell(value) for value in row)
                    ):
                        _append_continuation(
                            last_infrastructure,
                            row,
                            infrastructure_indices,
                            source_ref,
                        )
                    continue

                if district_cell is None:
                    if section != "relief_distributed_others" and any(
                        _cell(value) for value in row
                    ):
                        section_header_rows.append(row)
                    continue
                district, district_index = district_cell
                if section == "relief_distributed_others":
                    if district == "Total":
                        continue
                    text_values = [
                        _cell(value)
                        for value in row[district_index + 1 :]
                        if _cell(value)
                    ]
                    note = {
                        "district": district,
                        "baby_food_liquid_source_text": (
                            text_values[0] if len(text_values) > 0 else None
                        ),
                        "baby_food_solid_source_text": (
                            text_values[1] if len(text_values) > 1 else None
                        ),
                        "other_materials_source_text": (
                            " ".join(text_values[2:]) if len(text_values) > 2 else None
                        ),
                        "provenance": [source_ref],
                    }
                    if any(value for key, value in note.items() if key.endswith("_source_text")):
                        relief_material_notes.append(note)
                    continue

                if not any(
                    _NUMBER_CELL_RE.fullmatch(_cell(value))
                    for value in row[district_index + 1 :]
                    if _cell(value)
                ):
                    continue
                if section_indices is None:
                    section_indices = _semantic_header_map(
                        section,
                        section_header_rows,
                    )
                values = _semantic_values(row, section, section_indices)
                parsed = _impact_field(section, values)
                target = summary if district == "Total" else districts.setdefault(
                    district, {"district": district}
                )
                target[section] = parsed
                path = (
                    f"summary.{section}"
                    if district == "Total"
                    else f"districts[{district}].{section}"
                )
                field_provenance[path] = [source_ref]

    counts = {
        incident_type: sum(
            1 for record in infrastructure if record["incident_type"] == incident_type
        )
        for incident_type in _INFRASTRUCTURE_SECTIONS
    }
    for incident_type, declared in declared_infrastructure.items():
        if counts[incident_type] != declared:
            extraction_warnings.append(
                {
                    "code": "infrastructure_detail_count_mismatch",
                    "incident_type": incident_type,
                    "reported_count": declared,
                    "extracted_record_count": counts[incident_type],
                }
            )
    summary["infrastructure_incidents"] = {
        incident_type: declared_infrastructure.get(incident_type, counts[incident_type])
        for incident_type in _INFRASTRUCTURE_SECTIONS
    }
    summary["infrastructure_records_extracted"] = counts
    for incident_type in _INFRASTRUCTURE_SECTIONS:
        total_ref = declared_infrastructure_provenance.get(incident_type)
        if total_ref is not None:
            field_provenance[
                f"summary.infrastructure_incidents.{incident_type}"
            ] = [total_ref]
        record_refs = [
            reference
            for record in infrastructure
            if record["incident_type"] == incident_type
            for reference in record["provenance"]
        ]
        if record_refs:
            field_provenance[
                f"summary.infrastructure_records_extracted.{incident_type}"
            ] = record_refs
        elif total_ref is not None:
            field_provenance[
                f"summary.infrastructure_records_extracted.{incident_type}"
            ] = [total_ref]
    return {
        "summary": summary,
        "districts": districts,
        "field_provenance": field_provenance,
        "relief_material_notes": relief_material_notes,
        "infrastructure": infrastructure,
        "extraction_warnings": extraction_warnings,
    }
