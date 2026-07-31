"""Immutable file storage and append-only series for ASDMA bulletins."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .client import DownloadedBulletin
from .parser import BulletinParseError, parse_bulletin

DISTRICT_CSV_FIELDS = [
    "schema_version",
    "extractor_version",
    "report_date",
    "revision_id",
    "district",
    "affected_revenue_circles",
    "revenue_circles",
    "affected_villages",
    "affected_population",
    "crop_area_submerged_hectares",
    "relief_camps_open",
    "relief_distribution_centres_open",
    "relief_camp_occupants",
    "confirmed_deaths",
]

CIRCLE_CSV_FIELDS = [
    "schema_version",
    "extractor_version",
    "report_date",
    "revision_id",
    "district",
    "revenue_circle",
    "source_names",
    "affected_villages",
    "affected_population",
    "crop_area_submerged_hectares",
    "relief_camps_open",
    "relief_distribution_centres_open",
    "relief_camp_occupants",
    "confirmed_deaths",
]


def _write_immutable(path: Path, content: bytes) -> None:
    """Create an immutable file without ever exposing a partial final path."""

    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != content:
            raise RuntimeError(f"refusing to overwrite immutable file: {path}")
        return

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
        try:
            # A hard link is an atomic fail-if-exists publication operation.
            # Unlike os.replace(), it cannot overwrite a competing immutable
            # writer that reached the final path first.
            os.link(temporary_path, path)
        except FileExistsError:
            if path.read_bytes() != content:
                raise RuntimeError(
                    f"refusing to overwrite immutable file: {path}"
                ) from None
        directory_descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def _append_jsonl_once(path: Path, value: dict[str, Any], *, unique_key: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        for line in path.read_text().splitlines():
            if line and json.loads(line).get(unique_key) == value[unique_key]:
                return
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")


def _attach_revision_provenance(document: dict[str, Any], revision_id: str) -> None:
    """Complete parser row references with immutable artifact identity."""

    reference_lists = list(document.get("field_provenance", {}).values())
    reference_lists.extend(
        record.get("provenance", []) for record in document.get("infrastructure", [])
    )
    reference_lists.extend(
        record.get("provenance", [])
        for record in document.get("relief_material_notes", [])
    )
    for references in reference_lists:
        for reference in references:
            reference["source_revision_sha256"] = revision_id
            reference["report_date"] = document["report_date"]
            reference["extractor_version"] = document["extractor_version"]


def _district_csv_bytes(document: dict[str, Any]) -> bytes:
    from io import StringIO

    output = StringIO(newline="")
    writer = csv.DictWriter(
        output,
        fieldnames=DISTRICT_CSV_FIELDS,
        extrasaction="ignore",
        lineterminator="\n",
    )
    writer.writeheader()
    for district in document["districts"]:
        row = {
            "schema_version": document["schema_version"],
            "extractor_version": document["extractor_version"],
            "report_date": document["report_date"],
            "revision_id": document["revision_id"],
            **district,
        }
        if isinstance(row.get("revenue_circles"), list):
            row["revenue_circles"] = "|".join(row["revenue_circles"])
        writer.writerow(row)
    return output.getvalue().encode()


def _circle_csv_bytes(document: dict[str, Any]) -> bytes:
    from io import StringIO

    output = StringIO(newline="")
    writer = csv.DictWriter(
        output,
        fieldnames=CIRCLE_CSV_FIELDS,
        extrasaction="ignore",
        lineterminator="\n",
    )
    writer.writeheader()
    for district in document["districts"]:
        for circle in district.get("revenue_circle_data", []):
            row = {
                "schema_version": document["schema_version"],
                "extractor_version": document["extractor_version"],
                "report_date": document["report_date"],
                "revision_id": document["revision_id"],
                "district": district["district"],
                **circle,
            }
            row["source_names"] = "|".join(row.get("source_names", []))
            writer.writerow(row)
    return output.getvalue().encode()


def _persist_raw_download(
    download: DownloadedBulletin,
    *,
    data_dir: Path,
) -> tuple[str, Path, Path, dict[str, Any]]:
    """Preserve source evidence before parsing so layout drift cannot discard it."""

    digest = hashlib.sha256(download.content).hexdigest()
    requested_date = download.requested_date.isoformat()
    raw_dir = data_dir / "raw" / "asdma" / requested_date
    raw_pdf_path = raw_dir / f"{digest}.pdf"
    metadata_path = raw_dir / f"{digest}.metadata.json"
    if metadata_path.exists():
        metadata = json.loads(metadata_path.read_text())
    else:
        metadata = {
            "schema_version": 1,
            "requested_date": requested_date,
            "fetched_at": download.fetched_at.isoformat(),
            "source_url": download.source_url,
            "content_type": download.content_type,
            "sha256": digest,
            "size_bytes": len(download.content),
        }
    _write_immutable(raw_pdf_path, download.content)
    _write_immutable(metadata_path, _json_bytes(metadata))
    return digest, raw_pdf_path, metadata_path, metadata


def persist_bulletin(download: DownloadedBulletin, *, data_dir: Path) -> dict[str, Any]:
    """Parse and persist a bulletin without overwriting any prior revision."""

    requested_date = download.requested_date.isoformat()
    digest, raw_pdf_path, _, metadata = _persist_raw_download(
        download,
        data_dir=data_dir,
    )
    processed_dir = data_dir / "processed" / "asdma" / requested_date
    parsed = parse_bulletin(download.content)
    extractor_version = parsed["extractor_version"]
    artifact_id = f"{digest}-extractor-v{extractor_version}"
    json_path = processed_dir / f"{artifact_id}.json"
    csv_path = processed_dir / f"{artifact_id}.csv"
    circle_csv_path = processed_dir / f"{artifact_id}-circles.csv"
    if parsed["report_date"] != requested_date:
        raise BulletinParseError(
            f"requested {requested_date}, but PDF identifies itself as {parsed['report_date']}"
        )
    _attach_revision_provenance(parsed, digest)
    document = {
        **parsed,
        "revision_id": digest,
        "artifact_id": artifact_id,
        "source": metadata,
    }

    _write_immutable(json_path, _json_bytes(document))
    _write_immutable(csv_path, _district_csv_bytes(document))
    _write_immutable(circle_csv_path, _circle_csv_bytes(document))

    series_record = {
        "schema_version": document["schema_version"],
        "extractor_version": extractor_version,
        "report_date": document["report_date"],
        "revision_id": digest,
        "artifact_id": artifact_id,
        "fetched_at": metadata["fetched_at"],
        **document["summary"],
    }
    _append_jsonl_once(
        data_dir / "series" / "asdma_flood_summary.jsonl",
        series_record,
        unique_key="artifact_id",
    )

    return {
        "revision_id": digest,
        "artifact_id": artifact_id,
        "raw_pdf": str(raw_pdf_path),
        "json": str(json_path),
        "csv": str(csv_path),
        "circle_csv": str(circle_csv_path),
        "summary": document["summary"],
    }
