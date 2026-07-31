#!/usr/bin/env python3
"""Build the statewide season-loss checkpoint from retained ASDMA revisions."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import date, datetime, timedelta
from io import BytesIO
from pathlib import Path
from zoneinfo import ZoneInfo

import pdfplumber

from axom_flood.asdma.client import BulletinNotFound, fetch_bulletin
from axom_flood.asdma.storage import _json_bytes, _persist_raw_download, _write_immutable

IST = ZoneInfo("Asia/Kolkata")
_REPORT_DATE_RE = re.compile(r"as\s+on\s+(\d{2})-(\d{2})-(\d{4})", re.IGNORECASE)
_NUMBER_RE = re.compile(r"^[\d,\s]+$")


def _dates(start: date, end: date) -> list[date]:
    return [start + timedelta(days=offset) for offset in range((end - start).days + 1)]


def _retained_revision(data_dir: Path, report_date: date) -> tuple[Path, dict] | None:
    directory = data_dir / "raw" / "asdma" / report_date.isoformat()
    candidates: list[tuple[datetime, Path, dict]] = []
    for metadata_path in directory.glob("*.metadata.json"):
        metadata = json.loads(metadata_path.read_text())
        pdf_path = directory / f"{metadata['sha256']}.pdf"
        if pdf_path.exists():
            candidates.append(
                (datetime.fromisoformat(metadata["fetched_at"]), pdf_path, metadata)
            )
    if not candidates:
        return None
    _, pdf_path, metadata = max(candidates, key=lambda item: item[0])
    return pdf_path, metadata


def _cell(value: object) -> str:
    return " ".join(("" if value is None else str(value)).replace("\n", " ").split())


def _compact(value: object) -> str:
    return re.sub(r"[^a-z]", "", _cell(value).casefold())


def _daily_losses(content: bytes, expected_date: date) -> tuple[int, int]:
    totals: dict[str, int] = {}
    section: str | None = None
    with pdfplumber.open(BytesIO(content)) as document:
        heading = document.pages[0].extract_text() or ""
        date_match = _REPORT_DATE_RE.search(heading)
        if date_match is None:
            raise RuntimeError(f"{expected_date}: report heading date is missing")
        day, month, year = date_match.groups()
        actual_date = date(int(year), int(month), int(day))
        if actual_date != expected_date:
            raise RuntimeError(
                f"{expected_date}: retained PDF reports {actual_date.isoformat()}"
            )

        for page in document.pages:
            for table in page.extract_tables():
                for row in table:
                    if not row:
                        continue
                    first = _compact(row[0])
                    if first.startswith("humanliveslostconfirmed"):
                        section = "confirmed_deaths"
                        continue
                    if first.startswith("humanliveslostmissing"):
                        section = "people_reported_missing"
                        continue
                    if _cell(row[0]):
                        section = None
                        continue
                    if section is None:
                        continue
                    total_index = next(
                        (
                            index
                            for index, value in enumerate(row)
                            if _cell(value).replace(" ", "") == "Total"
                        ),
                        None,
                    )
                    if total_index is None:
                        continue
                    total_value = next(
                        (
                            _cell(value)
                            for value in row[total_index + 1 :]
                            if _cell(value)
                        ),
                        "",
                    )
                    if total_value.casefold() == "nil":
                        total = 0
                    elif _NUMBER_RE.fullmatch(total_value):
                        total = int(
                            total_value.replace(",", "").replace(" ", "")
                        )
                    else:
                        # Split header rows commonly contain a semantic "Total"
                        # column followed by "Male" or another subheading.
                        continue
                    if section in totals:
                        raise RuntimeError(
                            f"{expected_date}: duplicate {section} Total row"
                        )
                    totals[section] = total
    missing = {"confirmed_deaths", "people_reported_missing"} - totals.keys()
    if missing:
        raise RuntimeError(
            f"{expected_date}: missing loss totals: {', '.join(sorted(missing))}"
        )
    return totals["confirmed_deaths"], totals["people_reported_missing"]


def build_checkpoint(
    *,
    start: date,
    end: date,
    data_dir: Path,
    static_data_dir: Path,
    fetch_missing: bool,
) -> dict:
    reports: list[dict] = []
    missing_dates: list[str] = []
    unpublished_dates: list[str] = []
    for report_date in _dates(start, end):
        retained = _retained_revision(data_dir, report_date)
        if retained is None and fetch_missing:
            try:
                download = fetch_bulletin(report_date)
            except BulletinNotFound:
                unpublished_dates.append(report_date.isoformat())
                continue
            _, pdf_path, _, metadata = _persist_raw_download(
                download,
                data_dir=data_dir,
            )
            retained = pdf_path, metadata
        if retained is None:
            missing_dates.append(report_date.isoformat())
            continue

        pdf_path, metadata = retained
        content = pdf_path.read_bytes()
        revision_id = metadata["sha256"]
        if hashlib.sha256(content).hexdigest() != revision_id:
            raise RuntimeError(f"{pdf_path} source revision mismatch")
        confirmed_deaths, reported_missing = _daily_losses(content, report_date)
        source_artifact_url = f"data/asdma-source/{revision_id}.pdf"
        _write_immutable(
            static_data_dir / "asdma-source" / f"{revision_id}.pdf",
            content,
        )
        reports.append(
            {
                "report_date": report_date.isoformat(),
                "revision_id": revision_id,
                "newly_confirmed_deaths": confirmed_deaths,
                "newly_reported_missing": reported_missing,
                "source_artifact_url": source_artifact_url,
            }
        )

    if missing_dates:
        raise RuntimeError(
            "season checkpoint is incomplete; missing dates: " + ", ".join(missing_dates)
        )

    confirmed_deaths = sum(item["newly_confirmed_deaths"] for item in reports)
    reported_missing = sum(item["newly_reported_missing"] for item in reports)
    generated_at = max(
        json.loads(
            (
                data_dir
                / "raw"
                / "asdma"
                / item["report_date"]
                / f"{item['revision_id']}.metadata.json"
            ).read_text()
        )["fetched_at"]
        for item in reports
    )
    return {
        "schema_version": 2,
        "season_id": f"assam-flood-{end.year}",
        "season_label": f"{end.year} flood season",
        "season_start_date": start.isoformat(),
        "as_of_date": end.isoformat(),
        "statewide": {
            "confirmed_deaths": confirmed_deaths,
            "people_reported_missing": reported_missing,
        },
        "definitions": {
            "confirmed_deaths": (
                "The sum of deaths newly confirmed in each retained ASDMA daily "
                "flood report during the covered season."
            ),
            "people_reported_missing": (
                "The sum of people newly reported missing in each retained ASDMA "
                "daily flood report. It is not the number still missing."
            ),
        },
        "coverage": {
            "daily_report_start_date": start.isoformat(),
            "daily_report_end_date": end.isoformat(),
            "daily_reports_reviewed": len(reports),
            "unpublished_dates": unpublished_dates,
            "reports": reports,
        },
        "source": {
            "label": "ASDMA DRIMS daily flood report service",
            "url": "https://sdrf.assam.gov.in/dfr/download?type=flood",
        },
        "publication": {
            "state": "generated_checkpoint",
            "generated_at": generated_at,
            "generator": "build_asdma_season_losses-v1",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", required=True, type=date.fromisoformat)
    parser.add_argument("--end", required=True, type=date.fromisoformat)
    parser.add_argument("--data-dir", default="data", type=Path)
    parser.add_argument("--static-data-dir", default="static/data", type=Path)
    parser.add_argument("--output", default="static/data/asdma-season-losses.json", type=Path)
    parser.add_argument("--fetch-missing", action="store_true")
    args = parser.parse_args()
    if args.end < args.start:
        parser.error("--end must be on or after --start")
    checkpoint = build_checkpoint(
        start=args.start,
        end=args.end,
        data_dir=args.data_dir,
        static_data_dir=args.static_data_dir,
        fetch_missing=args.fetch_missing,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(_json_bytes(checkpoint))
    print(
        f"wrote {args.output}: {checkpoint['coverage']['daily_reports_reviewed']} "
        f"reports, {checkpoint['statewide']['confirmed_deaths']} deaths, "
        f"{checkpoint['statewide']['people_reported_missing']} missing reports"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
