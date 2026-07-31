"""Fail-closed validation and publication for ASDMA impact artifacts."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Callable, Iterable
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from jsonschema import Draft202012Validator, FormatChecker

from .client import DownloadedBulletin
from .storage import _json_bytes, _write_immutable

IST = ZoneInfo("Asia/Kolkata")
VALIDATOR_VERSION = 3
IMPACT_SCHEMA_VERSION = 2
VALIDATION_SCHEMA_VERSION = 1
POINTER_SCHEMA_VERSION = 2
DEFAULT_FRESHNESS_DAYS = 3
ROOT = Path(__file__).parents[3]
DEFAULT_BULLETIN_SCHEMA = ROOT / "schemas" / "asdma-bulletin.schema.json"

CORE_SUMMARY_FIELDS = (
    "affected_districts",
    "affected_revenue_circles",
    "affected_villages",
    "affected_population",
    "crop_area_submerged_hectares",
    "relief_camps_open",
    "relief_distribution_centres_open",
    "relief_camp_occupants",
    "confirmed_deaths",
    "missing_people",
)
BREAKDOWN_FIELDS = (
    "livestock_affected",
    "livestock_washed_away",
    "houses_damaged",
    "houses_damaged_others",
    "rescue_operations",
    "relief_distributed",
)
INFRASTRUCTURE_TYPES = (
    "road",
    "bridge",
    "embankment_breached",
    "embankment_affected",
)
FULL_ALLOWED_FIELDS = [
    "state_summary",
    "districts",
    "revenue_circles",
    "infrastructure",
    "rescue",
    "relief",
]


class ImpactPublicationError(RuntimeError):
    """The impact publication transaction could not complete."""


def _check(
    check_id: str,
    status: str,
    detail: str,
    *,
    field_paths: Iterable[str] = (),
) -> dict[str, Any]:
    return {
        "id": check_id,
        "status": status,
        "detail": detail,
        "field_paths": list(field_paths),
    }


def _numbers_equal(left: int | float, right: int | float) -> bool:
    return abs(float(left) - float(right)) <= 1e-6


def _sum_district_field(document: dict[str, Any], field: str) -> int | float | None:
    affected = set(document.get("affected_district_names", []))
    districts = {
        district["district"]: district for district in document.get("districts", [])
    }
    if not affected or not affected.issubset(districts):
        return None
    if not all(field in districts[name] for name in affected):
        return None
    return sum(float(districts[name][field]) for name in affected)


def _validate_schema(
    document: dict[str, Any],
    schema_path: Path,
) -> dict[str, Any]:
    schema = json.loads(schema_path.read_text())
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(document), key=lambda error: list(error.path))
    if not errors:
        return _check("bulletin_schema", "pass", "bulletin matches its versioned schema")
    details = "; ".join(
        f"{'.'.join(map(str, error.path)) or '<root>'}: {error.message}"
        for error in errors[:8]
    )
    return _check("bulletin_schema", "fail", details)


def _validate_source_identity(document: dict[str, Any]) -> dict[str, Any]:
    revision_id = document.get("revision_id")
    source = document.get("source", {})
    valid = (
        isinstance(revision_id, str)
        and source.get("sha256") == revision_id
        and document.get("artifact_id")
        == f"{revision_id}-extractor-v{document.get('extractor_version')}"
    )
    return _check(
        "source_identity",
        "pass" if valid else "fail",
        "source SHA, revision ID, and extractor artifact ID agree"
        if valid
        else "source SHA, revision ID, or extractor artifact ID disagree",
        field_paths=("revision_id", "artifact_id", "source.sha256"),
    )


def _validate_required_impact_fields(document: dict[str, Any]) -> dict[str, Any]:
    summary = document.get("summary", {})
    missing = [
        field
        for field in (*CORE_SUMMARY_FIELDS, *BREAKDOWN_FIELDS)
        if field not in summary
    ]
    for field in ("infrastructure_incidents", "infrastructure_records_extracted"):
        if field not in summary:
            missing.append(field)
    missing_top = [
        field
        for field in (
            "field_provenance",
            "relief_material_notes",
            "infrastructure",
            "extraction_warnings",
        )
        if field not in document
    ]
    missing.extend(missing_top)
    return _check(
        "required_impact_fields",
        "pass" if not missing else "fail",
        "all impact-v1 fields are present"
        if not missing
        else "missing impact-v1 fields: " + ", ".join(sorted(missing)),
        field_paths=missing,
    )


def _validate_non_negative(value: Any, path: str, errors: list[str]) -> None:
    if isinstance(value, bool):
        return
    if isinstance(value, (int, float)):
        if value < 0:
            errors.append(path)
        return
    if isinstance(value, dict):
        for key, child in value.items():
            _validate_non_negative(child, f"{path}.{key}".strip("."), errors)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _validate_non_negative(child, f"{path}[{index}]", errors)


def _validate_non_negative_metrics(document: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    _validate_non_negative(document.get("summary", {}), "summary", errors)
    for index, district in enumerate(document.get("districts", [])):
        for field in (*CORE_SUMMARY_FIELDS, *BREAKDOWN_FIELDS):
            if field in district:
                _validate_non_negative(
                    district[field],
                    f"districts[{index}].{field}",
                    errors,
                )
    return _check(
        "non_negative_metrics",
        "pass" if not errors else "fail",
        "all official numeric impact fields are non-negative"
        if not errors
        else "negative official values at: " + ", ".join(errors),
        field_paths=errors,
    )


def _validate_breakdowns(document: dict[str, Any]) -> dict[str, Any]:
    failures: list[str] = []
    summary = document.get("summary", {})
    for field in ("livestock_affected", "livestock_washed_away"):
        value = summary.get(field, {})
        if value and not _numbers_equal(
            value.get("total", -1),
            sum(value.get(key, 0) for key in ("big_animals", "small_animals", "poultry")),
        ):
            failures.append(f"summary.{field}")
    houses = summary.get("houses_damaged", {})
    if houses:
        if not _numbers_equal(
            houses.get("fully_total", -1),
            houses.get("fully_kutcha", 0) + houses.get("fully_pucca", 0),
        ):
            failures.append("summary.houses_damaged.fully_total")
        if not _numbers_equal(
            houses.get("partially_total", -1),
            houses.get("partially_kutcha", 0) + houses.get("partially_pucca", 0),
        ):
            failures.append("summary.houses_damaged.partially_total")
    others = summary.get("houses_damaged_others", {})
    if others and not _numbers_equal(
        others.get("other_total", -1),
        others.get("other_huts", 0) + others.get("cattle_sheds", 0),
    ):
        failures.append("summary.houses_damaged_others.other_total")
    return _check(
        "component_arithmetic",
        "pass" if not failures else "fail",
        "livestock and house subtotals reconcile"
        if not failures
        else "component totals do not reconcile",
        field_paths=failures,
    )


def _validate_district_arithmetic(document: dict[str, Any]) -> dict[str, Any]:
    summary = document.get("summary", {})
    failures: list[str] = []
    if summary.get("affected_districts") != len(
        document.get("affected_district_names", [])
    ):
        failures.append("summary.affected_districts")
    for field in CORE_SUMMARY_FIELDS[1:]:
        district_total = _sum_district_field(document, field)
        if (
            district_total is not None
            and field in summary
            and not _numbers_equal(summary[field], district_total)
        ):
            failures.append(f"summary.{field}")
    return _check(
        "district_arithmetic",
        "pass" if not failures else "fail",
        "state totals reconcile with complete district detail"
        if not failures
        else "state and district totals disagree",
        field_paths=failures,
    )


def _validate_infrastructure(document: dict[str, Any]) -> list[dict[str, Any]]:
    summary = document.get("summary", {})
    declared = summary.get("infrastructure_incidents", {})
    extracted = summary.get("infrastructure_records_extracted", {})
    records = document.get("infrastructure", [])
    actual = {
        incident_type: sum(
            record.get("incident_type") == incident_type for record in records
        )
        for incident_type in INFRASTRUCTURE_TYPES
    }
    failures = [
        f"summary.infrastructure_records_extracted.{incident_type}"
        for incident_type in INFRASTRUCTURE_TYPES
        if extracted.get(incident_type) != actual[incident_type]
    ]
    checks = [
        _check(
            "infrastructure_record_count",
            "pass" if not failures else "fail",
            "extracted infrastructure counts equal retained records"
            if not failures
            else "extracted infrastructure count does not equal retained records",
            field_paths=failures,
        )
    ]

    mismatches = [
        incident_type
        for incident_type in INFRASTRUCTURE_TYPES
        if declared.get(incident_type) != actual[incident_type]
    ]
    source_warnings = {
        warning.get("incident_type"): warning
        for warning in document.get("extraction_warnings", [])
        if warning.get("code") == "infrastructure_detail_count_mismatch"
    }
    warning_matches = all(
        source_warnings.get(incident_type)
        and source_warnings[incident_type].get("reported_count")
        == declared.get(incident_type)
        and source_warnings[incident_type].get("extracted_record_count")
        == actual[incident_type]
        for incident_type in mismatches
    )
    unexpected_warnings = [
        warning
        for warning in document.get("extraction_warnings", [])
        if warning.get("code") != "infrastructure_detail_count_mismatch"
        or warning.get("incident_type") not in mismatches
    ]
    status = (
        "pass"
        if not mismatches and not unexpected_warnings
        else "warn"
        if mismatches and warning_matches and not unexpected_warnings
        else "fail"
    )
    checks.append(
        _check(
            "infrastructure_source_reconciliation",
            status,
            "reported infrastructure totals reconcile with detail"
            if status == "pass"
            else "approved source/detail mismatch: " + ", ".join(mismatches)
            if status == "warn"
            else "unexplained infrastructure mismatch or warning",
            field_paths=[
                f"summary.infrastructure_incidents.{incident_type}"
                for incident_type in mismatches
            ],
        )
    )

    coordinate_failures: list[str] = []
    for index, record in enumerate(records):
        coordinate_state = record.get("coordinate_validation")
        longitude = record.get("longitude")
        latitude = record.get("latitude")
        match_scope = record.get("match_scope")
        if coordinate_state == "valid":
            if (
                longitude is None
                or latitude is None
                or not 89.5 <= longitude <= 97.5
                or not 24 <= latitude <= 29.5
                or match_scope != "coordinates"
            ):
                coordinate_failures.append(f"infrastructure[{index}]")
        elif match_scope == "coordinates":
            coordinate_failures.append(f"infrastructure[{index}]")
    checks.append(
        _check(
            "coordinate_scope",
            "pass" if not coordinate_failures else "fail",
            "coordinate points and fallback scopes obey the Assam envelope"
            if not coordinate_failures
            else "invalid coordinates were promoted or valid coordinates lost",
            field_paths=coordinate_failures,
        )
    )
    return checks


def _validate_provenance(document: dict[str, Any]) -> dict[str, Any]:
    failures: list[str] = []
    revision_id = document.get("revision_id")
    report_date = document.get("report_date")
    extractor_version = document.get("extractor_version")
    reference_lists = list(document.get("field_provenance", {}).items())
    for index, record in enumerate(document.get("infrastructure", [])):
        reference_lists.append((f"infrastructure[{index}]", record.get("provenance", [])))
    for index, record in enumerate(document.get("relief_material_notes", [])):
        reference_lists.append(
            (f"relief_material_notes[{index}]", record.get("provenance", []))
        )
    for path, references in reference_lists:
        if not references:
            failures.append(path)
            continue
        for reference in references:
            if (
                reference.get("source_revision_sha256") != revision_id
                or reference.get("report_date") != report_date
                or reference.get("extractor_version") != extractor_version
                or any(reference.get(key, 0) < 1 for key in ("page", "table", "row"))
            ):
                failures.append(path)
                break
    return _check(
        "field_provenance",
        "pass" if not failures else "fail",
        "all extracted values resolve to exact source rows and revision"
        if not failures
        else "missing or inconsistent source provenance",
        field_paths=failures,
    )


def _validate_temporal(
    document: dict[str, Any],
    *,
    now: datetime,
) -> dict[str, Any]:
    try:
        report_date = date.fromisoformat(document["report_date"])
        fetched_at = datetime.fromisoformat(document["source"]["fetched_at"])
        if fetched_at.tzinfo is None:
            raise ValueError("fetched_at lacks timezone")
    except (KeyError, TypeError, ValueError) as exc:
        return _check("temporal_contract", "fail", f"invalid report/fetch time: {exc}")
    now_ist = now.astimezone(IST)
    fetched_ist = fetched_at.astimezone(IST)
    valid = report_date <= now_ist.date() and fetched_ist.date() >= report_date
    return _check(
        "temporal_contract",
        "pass" if valid else "fail",
        "report date and fetch time are chronologically valid"
        if valid
        else "report is future-dated or fetch precedes report date",
        field_paths=("report_date", "source.fetched_at"),
    )


def validate_bulletin(
    document: dict[str, Any],
    *,
    now: datetime,
    schema_path: Path = DEFAULT_BULLETIN_SCHEMA,
) -> list[dict[str, Any]]:
    """Run independent deterministic validation over one extracted bulletin."""

    checks = [
        _validate_schema(document, schema_path),
        _validate_source_identity(document),
        _validate_required_impact_fields(document),
        _validate_non_negative_metrics(document),
        _validate_breakdowns(document),
        _validate_district_arithmetic(document),
        _validate_provenance(document),
        _validate_temporal(document, now=now),
    ]
    checks.extend(_validate_infrastructure(document))
    return checks


def _current_pointer(data_dir: Path) -> dict[str, Any] | None:
    path = data_dir / "processed" / "asdma-impact" / "impact-current.json"
    return json.loads(path.read_text()) if path.exists() else None


def _publication_state(
    document: dict[str, Any],
    checks: list[dict[str, Any]],
    *,
    now: datetime,
    current: dict[str, Any] | None,
    freshness_days: int,
) -> tuple[str, str, list[str], list[str]]:
    failures = [check["id"] for check in checks if check["status"] == "fail"]
    warnings = [check["id"] for check in checks if check["status"] == "warn"]
    if failures:
        return "quarantined", "none", [], failures

    partial = warnings == ["infrastructure_source_reconciliation"]
    if partial:
        mismatched_types = [
            warning["incident_type"]
            for warning in document.get("extraction_warnings", [])
            if warning.get("code") == "infrastructure_detail_count_mismatch"
        ]
        profile = "impact-v1-infrastructure-count-only"
        allowed_fields = [
            *[field for field in FULL_ALLOWED_FIELDS if field != "infrastructure"],
            "infrastructure_filtered",
            *[
                f"infrastructure_except:{incident_type}"
                for incident_type in mismatched_types
            ],
        ]
    elif warnings:
        return "quarantined", "none", [], warnings
    else:
        profile = "impact-v1"
        allowed_fields = FULL_ALLOWED_FIELDS

    report_date = date.fromisoformat(document["report_date"])
    current_date = date.fromisoformat(current["report_date"]) if current else None
    if current_date and report_date < current_date:
        return "historical", profile, allowed_fields, []
    if (
        current
        and report_date == current_date
        and current["revision_id"] != document["revision_id"]
    ):
        candidate_fetch = datetime.fromisoformat(document["source"]["fetched_at"])
        current_fetch = datetime.fromisoformat(current["fetched_at"])
        if candidate_fetch <= current_fetch:
            return "superseded", profile, allowed_fields, []
    if (now.astimezone(IST).date() - report_date).days > freshness_days:
        return "historical", profile, allowed_fields, []
    return (
        "validated_partial" if partial else "validated",
        profile,
        allowed_fields,
        [],
    )


def _flatten_circles(document: dict[str, Any]) -> list[dict[str, Any]]:
    circles: list[dict[str, Any]] = []
    for district in document["districts"]:
        for circle in district.get("revenue_circle_data", []):
            circles.append({"district": district["district"], **circle})
    return circles


def _impact_document(
    bulletin: dict[str, Any],
    validation: dict[str, Any],
) -> dict[str, Any]:
    excluded_incident_types = {
        item.split(":", 1)[1]
        for item in validation["allowed_fields"]
        if item.startswith("infrastructure_except:")
    }
    infrastructure = []
    for source_record in bulletin["infrastructure"]:
        if source_record["incident_type"] in excluded_incident_types:
            continue
        record = dict(source_record)
        if record["coordinate_validation"] != "valid":
            record["longitude"] = None
            record["latitude"] = None
        infrastructure.append(record)
    summary = dict(bulletin["summary"])
    rescue = summary.pop("rescue_operations")
    distributed_relief = summary.pop("relief_distributed")
    return {
        "schema_version": IMPACT_SCHEMA_VERSION,
        "report_date": bulletin["report_date"],
        "revision_id": bulletin["revision_id"],
        "extractor_version": bulletin["extractor_version"],
        "fetched_at": bulletin["source"]["fetched_at"],
        "publication": {
            "state": validation["state"],
            "profile": validation["profile"],
            "validated_at": validation["validated_at"],
            "allowed_fields": validation["allowed_fields"],
        },
        "source": {
            "url": bulletin["source"]["source_url"],
            "artifact_url": (
                f"data/asdma-source/{bulletin['revision_id']}.pdf"
            ),
            "sha256": bulletin["revision_id"],
            "bulletin_artifact_id": bulletin["artifact_id"],
        },
        "state_summary": summary,
        "districts": bulletin["districts"],
        "revenue_circles": _flatten_circles(bulletin),
        "infrastructure": infrastructure,
        "rescue": rescue,
        "relief": {
            "distributed": distributed_relief,
            "material_notes": bulletin["relief_material_notes"],
        },
        "validation": {
            "validation_id": validation["validation_id"],
            "checks": validation["checks"],
            "warnings": validation["warnings"],
        },
    }


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def _artifact_names(document: dict[str, Any]) -> tuple[str, str, str]:
    stem = (
        f"{document['revision_id']}-extractor-v{document['extractor_version']}"
        f"-validator-v{VALIDATOR_VERSION}"
    )
    return (
        f"impact-{stem}.json",
        f"validation-{stem}.json",
        f"validation-{stem}",
    )


def _publish_source_artifact(
    bulletin: dict[str, Any],
    *,
    data_dir: Path,
    static_data_dir: Path,
) -> str:
    revision_id = bulletin["revision_id"]
    source_path = (
        data_dir
        / "raw"
        / "asdma"
        / bulletin["report_date"]
        / f"{revision_id}.pdf"
    )
    if not source_path.exists():
        raise ImpactPublicationError(
            f"retained source PDF is missing for revision {revision_id}"
        )
    content = source_path.read_bytes()
    if not content.startswith(b"%PDF"):
        raise ImpactPublicationError("retained ASDMA source is not a PDF")
    if hashlib.sha256(content).hexdigest() != revision_id:
        raise ImpactPublicationError("retained ASDMA source SHA-256 mismatch")
    artifact_url = f"data/asdma-source/{revision_id}.pdf"
    _write_immutable(static_data_dir / "asdma-source" / f"{revision_id}.pdf", content)
    return artifact_url


def _history_manifest(static_data_dir: Path) -> dict[str, Any]:
    reports_by_revision: dict[str, dict[str, Any]] = {}
    for path in static_data_dir.glob("impact-*-validator-v*.json"):
        impact = json.loads(path.read_text())
        if impact.get("schema_version") != IMPACT_SCHEMA_VERSION:
            continue
        publication = impact.get("publication", {})
        state = publication.get("state")
        if state not in {
            "validated",
            "validated_partial",
            "historical",
            "superseded",
        }:
            continue
        report = {
            "report_date": impact["report_date"],
            "revision_id": impact["revision_id"],
            "extractor_version": impact["extractor_version"],
            "fetched_at": impact["fetched_at"],
            "publication_state": state,
            "profile": publication["profile"],
            "validated_at": publication["validated_at"],
            "impact_url": f"data/{path.name}",
            "source_url": impact["source"]["url"],
            "source_artifact_url": impact["source"]["artifact_url"],
        }
        existing = reports_by_revision.get(impact["revision_id"])
        if existing is None or report["validated_at"] > existing["validated_at"]:
            reports_by_revision[impact["revision_id"]] = report
    reports = list(reports_by_revision.values())
    reports.sort(
        key=lambda report: (
            report["report_date"],
            report["fetched_at"],
            report["revision_id"],
        ),
        reverse=True,
    )
    return {
        "schema_version": 2,
        "updated_at": max(
            (report["validated_at"] for report in reports),
            default=datetime.now(IST).isoformat(),
        ),
        "reports": reports,
    }


def _write_status_manifest(
    *,
    validation: dict[str, Any],
    output_dir: Path,
    static_data_dir: Path,
) -> None:
    current_path = output_dir / "impact-current.json"
    current = json.loads(current_path.read_text()) if current_path.exists() else None
    status = {
        "schema_version": 1,
        "updated_at": validation["validated_at"],
        "latest_attempt": {
            "report_date": validation["report_date"],
            "revision_id": validation["revision_id"],
            "extractor_version": validation["extractor_version"],
            "validated_at": validation["validated_at"],
            "state": validation["state"],
            "validation_id": validation["validation_id"],
            "failures": validation["failures"],
        },
        "current_valid": (
            {
                "report_date": current["report_date"],
                "revision_id": current["revision_id"],
                "publication_state": current["publication_state"],
                "impact_url": current["impact_url"],
            }
            if current is not None
            else None
        ),
    }
    content = _json_bytes(status)
    _atomic_write(output_dir / "impact-status.json", content)
    _atomic_write(static_data_dir / "impact-status.json", content)


def _write_history_manifest(
    *,
    output_dir: Path,
    static_data_dir: Path,
) -> None:
    content = _json_bytes(_history_manifest(static_data_dir))
    for path in (
        output_dir / "impact-history.json",
        static_data_dir / "impact-history.json",
    ):
        if path.exists() and path.read_bytes() == content:
            continue
        _atomic_write(path, content)


def publish_impact(
    bulletin_path: Path,
    *,
    data_dir: Path,
    static_data_dir: Path,
    now: datetime | None = None,
    freshness_days: int = DEFAULT_FRESHNESS_DAYS,
    before_pointer_update: Callable[[], None] | None = None,
) -> dict[str, Any]:
    """Validate and publish one extractor artifact without exposing failures."""

    now = now or datetime.now(IST)
    bulletin = json.loads(bulletin_path.read_text())
    impact_name, validation_name, validation_id = _artifact_names(bulletin)
    output_dir = data_dir / "processed" / "asdma-impact"
    validation_path = output_dir / validation_name
    impact_path = output_dir / impact_name
    current = _current_pointer(data_dir)

    if validation_path.exists():
        validation = json.loads(validation_path.read_text())
        impact_exists = validation["impact_url"] is not None
        if impact_exists:
            _publish_source_artifact(
                bulletin,
                data_dir=data_dir,
                static_data_dir=static_data_dir,
            )
            impact = _impact_document(bulletin, validation)
            impact_bytes = _json_bytes(impact)
            _write_immutable(impact_path, impact_bytes)
            _write_immutable(static_data_dir / impact_name, impact_bytes)
            _write_history_manifest(
                output_dir=output_dir,
                static_data_dir=static_data_dir,
            )
    else:
        checks = validate_bulletin(bulletin, now=now)
        state, profile, allowed_fields, policy_failures = _publication_state(
            bulletin,
            checks,
            now=now,
            current=current,
            freshness_days=freshness_days,
        )
        validation = {
            "schema_version": VALIDATION_SCHEMA_VERSION,
            "validator_version": VALIDATOR_VERSION,
            "validation_id": validation_id,
            "revision_id": bulletin["revision_id"],
            "extractor_version": bulletin["extractor_version"],
            "report_date": bulletin["report_date"],
            "validated_at": now.isoformat(),
            "state": state,
            "profile": profile,
            "allowed_fields": allowed_fields,
            "checks": checks,
            "warnings": [
                check["id"] for check in checks if check["status"] == "warn"
            ],
            "failures": [
                *[check["id"] for check in checks if check["status"] == "fail"],
                *policy_failures,
            ],
            "impact_url": (
                f"data/{impact_name}"
                if state
                in {"validated", "validated_partial", "historical", "superseded"}
                else None
            ),
        }
        _write_immutable(validation_path, _json_bytes(validation))
        impact_exists = validation["impact_url"] is not None
        if impact_exists:
            _publish_source_artifact(
                bulletin,
                data_dir=data_dir,
                static_data_dir=static_data_dir,
            )
            impact = _impact_document(bulletin, validation)
            impact_bytes = _json_bytes(impact)
            _write_immutable(impact_path, impact_bytes)
            _write_immutable(static_data_dir / impact_name, impact_bytes)
            _write_history_manifest(
                output_dir=output_dir,
                static_data_dir=static_data_dir,
            )

    pointer_eligible = validation["state"] in {"validated", "validated_partial"}
    if pointer_eligible and current and current["revision_id"] != bulletin["revision_id"]:
        candidate_date = date.fromisoformat(bulletin["report_date"])
        current_date = date.fromisoformat(current["report_date"])
        candidate_fetch = datetime.fromisoformat(bulletin["source"]["fetched_at"])
        current_fetch = datetime.fromisoformat(current["fetched_at"])
        if candidate_date < current_date or (
            candidate_date == current_date and candidate_fetch <= current_fetch
        ):
            pointer_eligible = False
    pointer_updated = False
    if pointer_eligible:
        pointer = {
            "schema_version": POINTER_SCHEMA_VERSION,
            "updated_at": validation["validated_at"],
            "report_date": bulletin["report_date"],
            "revision_id": bulletin["revision_id"],
            "extractor_version": bulletin["extractor_version"],
            "fetched_at": bulletin["source"]["fetched_at"],
            "publication_state": validation["state"],
            "profile": validation["profile"],
            "impact_url": validation["impact_url"],
            "validation_id": validation["validation_id"],
            "source_url": bulletin["source"]["source_url"],
            "source_artifact_url": (
                f"data/asdma-source/{bulletin['revision_id']}.pdf"
            ),
        }
        pointer_bytes = _json_bytes(pointer)
        internal_pointer_path = output_dir / "impact-current.json"
        public_pointer_path = static_data_dir / "impact-current.json"
        already_current = (
            internal_pointer_path.exists()
            and public_pointer_path.exists()
            and internal_pointer_path.read_bytes() == pointer_bytes
            and public_pointer_path.read_bytes() == pointer_bytes
        )
        if not already_current:
            if before_pointer_update is not None:
                before_pointer_update()
            _atomic_write(internal_pointer_path, pointer_bytes)
            _atomic_write(public_pointer_path, pointer_bytes)
            pointer_updated = True

    _write_status_manifest(
        validation=validation,
        output_dir=output_dir,
        static_data_dir=static_data_dir,
    )

    return {
        "revision_id": bulletin["revision_id"],
        "state": validation["state"],
        "profile": validation["profile"],
        "validation": str(validation_path),
        "impact": str(impact_path) if impact_exists else None,
        "pointer_updated": pointer_updated,
        "warnings": validation["warnings"],
        "failures": validation["failures"],
    }


def quarantine_source_failure(
    download: DownloadedBulletin,
    *,
    data_dir: Path,
    static_data_dir: Path,
    error: Exception,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Persist a validation record for a source revision that could not parse."""

    now = now or datetime.now(IST)
    revision_id = hashlib.sha256(download.content).hexdigest()
    validation_id = (
        f"validation-{revision_id}-extractor-unknown-validator-v{VALIDATOR_VERSION}"
    )
    validation_name = f"{validation_id}.json"
    validation_path = (
        data_dir / "processed" / "asdma-impact" / validation_name
    )
    if not validation_path.exists():
        validation = {
            "schema_version": VALIDATION_SCHEMA_VERSION,
            "validator_version": VALIDATOR_VERSION,
            "validation_id": validation_id,
            "revision_id": revision_id,
            "extractor_version": None,
            "report_date": download.requested_date.isoformat(),
            "validated_at": now.isoformat(),
            "state": "quarantined",
            "profile": "none",
            "allowed_fields": [],
            "checks": [
                _check(
                    "source_structure",
                    "fail",
                    f"{type(error).__name__}: {error}",
                )
            ],
            "warnings": [],
            "failures": ["source_structure"],
            "impact_url": None,
        }
        _write_immutable(validation_path, _json_bytes(validation))
    else:
        validation = json.loads(validation_path.read_text())
    _write_status_manifest(
        validation=validation,
        output_dir=data_dir / "processed" / "asdma-impact",
        static_data_dir=static_data_dir,
    )
    return {
        "revision_id": revision_id,
        "state": "quarantined",
        "profile": "none",
        "validation": str(validation_path),
        "impact": None,
        "pointer_updated": False,
        "warnings": [],
        "failures": ["source_structure"],
    }


def verify_impact_publication(
    *,
    base_url: str,
    expected_pointer: dict[str, Any],
    timeout_seconds: float = 20,
    fetch_json: Callable[[str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Verify that production serves both the intended pointer and artifact."""

    base = base_url.rstrip("/")

    def default_fetch(url: str) -> dict[str, Any]:
        response = httpx.get(url, timeout=timeout_seconds, follow_redirects=True)
        response.raise_for_status()
        return response.json()

    fetch = fetch_json or default_fetch
    pointer_url = f"{base}/data/impact-current.json"
    actual_pointer = fetch(pointer_url)
    for field in ("revision_id", "report_date", "publication_state", "impact_url"):
        if actual_pointer.get(field) != expected_pointer.get(field):
            raise ImpactPublicationError(
                f"production pointer {field} mismatch: expected "
                f"{expected_pointer.get(field)!r}, got {actual_pointer.get(field)!r}"
            )
    impact_url = f"{base}/{actual_pointer['impact_url'].lstrip('/')}"
    impact = fetch(impact_url)
    if impact.get("revision_id") != expected_pointer["revision_id"]:
        raise ImpactPublicationError("production impact artifact revision mismatch")
    if impact.get("publication", {}).get("state") != expected_pointer["publication_state"]:
        raise ImpactPublicationError("production impact publication state mismatch")
    return {
        "pointer_url": pointer_url,
        "impact_url": impact_url,
        "revision_id": expected_pointer["revision_id"],
        "publication_state": expected_pointer["publication_state"],
    }
