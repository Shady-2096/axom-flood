"""Reproducible Assam subset ingest from UDISE-compatible bulk CSV data."""

from __future__ import annotations

import csv
import hashlib
import json
import tempfile
import zipfile
from pathlib import Path
from typing import BinaryIO

import httpx

DEFAULT_SOURCE_URL = (
    "https://raw.githubusercontent.com/datameet/udise_schools/master/data/udise_schools.zip"
)
FIELDS = [
    "udise_code",
    "school_name",
    "district",
    "village",
    "longitude",
    "latitude",
    "school_category",
    "management",
]
ALIASES = {
    "udise_code": ("schcd", "udise_code"),
    "school_name": ("schname", "school_name"),
    "district": ("dtname", "district"),
    "village": ("vilname", "village"),
    "longitude": ("lon", "longitude"),
    "latitude": ("lat", "latitude"),
    "school_category": ("school_cat", "school_category"),
    "management": ("management",),
}


def _first(row: dict[str, str], names: tuple[str, ...]) -> str:
    return next((row.get(name, "").strip() for name in names if row.get(name, "").strip()), "")


def _valid_coordinate(longitude: str, latitude: str) -> bool:
    try:
        lon, lat = float(longitude), float(latitude)
    except ValueError:
        return False
    return 89 <= lon <= 97 and 23 <= lat <= 29


def _download(url: str, target: BinaryIO) -> str:
    digest = hashlib.sha256()
    with httpx.stream(
        "GET",
        url,
        follow_redirects=True,
        timeout=120,
        headers={"User-Agent": "AxomFloodData/0.1"},
    ) as response:
        response.raise_for_status()
        for chunk in response.iter_bytes():
            digest.update(chunk)
            target.write(chunk)
    return digest.hexdigest()


def ingest_assam_schools(
    *,
    source: str,
    data_dir: Path,
    source_label: str = "datameet_udise_2021_snapshot",
) -> dict[str, object]:
    with tempfile.NamedTemporaryFile(suffix=".zip") as temporary:
        if source.startswith(("http://", "https://")):
            source_sha256 = _download(source, temporary)
        else:
            raw = Path(source).read_bytes()
            source_sha256 = hashlib.sha256(raw).hexdigest()
            temporary.write(raw)
        temporary.flush()

        output_dir = data_dir / "reference" / "udise"
        output_dir.mkdir(parents=True, exist_ok=True)
        csv_path = output_dir / f"assam-schools-{source_sha256}.csv"
        metadata_path = output_dir / f"assam-schools-{source_sha256}.metadata.json"
        if csv_path.exists() and metadata_path.exists():
            metadata = json.loads(metadata_path.read_text())
            return {**metadata, "csv": str(csv_path), "metadata": str(metadata_path)}

        count = 0
        coordinate_count = 0
        with zipfile.ZipFile(temporary.name) as archive:
            csv_names = [name for name in archive.namelist() if name.lower().endswith(".csv")]
            if len(csv_names) != 1:
                raise ValueError("UDISE archive must contain exactly one CSV")
            with (
                archive.open(csv_names[0]) as raw_csv,
                csv_path.open("w", newline="", encoding="utf-8") as output,
            ):
                import io

                reader = csv.DictReader(io.TextIOWrapper(raw_csv, encoding="utf-8-sig"))
                writer = csv.DictWriter(output, fieldnames=FIELDS, lineterminator="\n")
                writer.writeheader()
                for row in reader:
                    state = (row.get("stname") or row.get("state") or "").strip().casefold()
                    if state != "assam":
                        continue
                    record = {field: _first(row, ALIASES[field]) for field in FIELDS}
                    if not record["udise_code"] or not record["school_name"]:
                        continue
                    if not _valid_coordinate(record["longitude"], record["latitude"]):
                        record["longitude"] = ""
                        record["latitude"] = ""
                    else:
                        coordinate_count += 1
                    writer.writerow(record)
                    count += 1

    metadata = {
        "schema_version": 1,
        "source_url": (
            source
            if source.startswith(("http://", "https://"))
            else DEFAULT_SOURCE_URL if source_label == "datameet_udise_2021_snapshot" else None
        ),
        "source_label": source_label,
        "source_sha256": source_sha256,
        "school_count": count,
        "schools_with_coordinates": coordinate_count,
        "staleness_warning": (
            "Community mirror snapshot dated 2021; refresh from an official UDISE export "
            "before operational navigation."
        ),
    }
    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")
    return {**metadata, "csv": str(csv_path), "metadata": str(metadata_path)}
