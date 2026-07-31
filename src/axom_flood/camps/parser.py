"""Table-oriented extraction for dedicated district relief-camp PDFs."""

from __future__ import annotations

import re
from io import BytesIO
from typing import Any

import pdfplumber

EXTRACTOR_VERSION = 1
_SERIAL_RE = re.compile(r"^\s*\d+\s*$")
_CIRCLE_RE = re.compile(
    r"(?:under|in)\s+([A-Za-z][A-Za-z .()-]+?)\s+Revenue\s+Circle", re.IGNORECASE
)


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(str(value).split()).strip()
    return cleaned or None


def _number(value: Any, low: float, high: float) -> float | None:
    raw = (_clean(value) or "").replace("N", "").replace("E", "").strip()
    try:
        parsed = float(raw)
    except ValueError:
        return None
    return parsed if low <= parsed <= high else None


def _headings(page: Any) -> list[tuple[float, str]]:
    lines: dict[int, list[dict[str, Any]]] = {}
    for word in page.extract_words():
        lines.setdefault(round(word["top"]), []).append(word)
    ordered = [
        (float(top), " ".join(word["text"] for word in sorted(words, key=lambda item: item["x0"])))
        for top, words in sorted(lines.items())
    ]
    headings: list[tuple[float, str]] = []
    for index in range(len(ordered)):
        window = " ".join(text for _, text in ordered[index : index + 3])
        match = _CIRCLE_RE.search(window)
        if match:
            headings.append((ordered[index][0], " ".join(match.group(1).split())))
    return headings


def _header_map(row: list[Any]) -> dict[str, int] | None:
    mapping: dict[str, int] = {}
    for index, value in enumerate(row):
        cell = (_clean(value) or "").lower()
        if ("relief camp" in cell or "name of camp" in cell) and "manager" not in cell:
            mapping["name"] = index
        elif "latitude" in cell:
            mapping["latitude"] = index
        elif "longitude" in cell:
            mapping["longitude"] = index
        elif "village" in cell:
            mapping["village"] = index
        elif "contact number" in cell or cell == "contact no":
            mapping["contact_phone"] = index
        elif "capacity" in cell:
            mapping["capacity_estimate"] = index
    return mapping if "name" in mapping else None


def parse_dedicated_camp_pdf(
    content: bytes,
    *,
    district: str,
    source_document_id: str,
    source_url: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    camps: list[dict[str, Any]] = []
    review: list[dict[str, Any]] = []
    current_circle: str | None = None
    mapping: dict[str, int] | None = None

    with pdfplumber.open(BytesIO(content)) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            headings = _headings(page)
            found_tables = page.find_tables()
            for table_index, table in enumerate(found_tables, start=1):
                table_top = table.bbox[1]
                before = [item for item in headings if item[0] < table_top]
                if before:
                    current_circle = max(before, key=lambda item: item[0])[1]
                rows = table.extract()
                for row in rows:
                    candidate_map = _header_map(row)
                    if candidate_map:
                        mapping = candidate_map
                        continue
                    if not row or not _SERIAL_RE.match(_clean(row[0]) or ""):
                        continue
                    active = mapping
                    if active is None and len(row) >= 7:
                        active = {
                            "name": 1,
                            "latitude": 2,
                            "longitude": 3,
                            "village": 4,
                            "contact_phone": 6,
                        }
                    if active is None:
                        continue
                    name = _clean(row[active["name"]]) if active["name"] < len(row) else None
                    if not name:
                        continue
                    latitude = (
                        _number(row[active["latitude"]], 23.0, 29.0)
                        if "latitude" in active and active["latitude"] < len(row)
                        else None
                    )
                    longitude = (
                        _number(row[active["longitude"]], 89.0, 97.0)
                        if "longitude" in active and active["longitude"] < len(row)
                        else None
                    )
                    record = {
                        "schema_version": 1,
                        "district": district,
                        "revenue_circle": current_circle,
                        "name_raw": name,
                        "village": (
                            _clean(row[active["village"]])
                            if "village" in active and active["village"] < len(row)
                            else None
                        ),
                        "coordinates": (
                            [longitude, latitude]
                            if latitude is not None and longitude is not None
                            else None
                        ),
                        "contact_phone": (
                            _clean(row[active["contact_phone"]])
                            if "contact_phone" in active
                            and active["contact_phone"] < len(row)
                            else None
                        ),
                        "capacity_estimate": (
                            int(_number(row[active["capacity_estimate"]], 0, 1_000_000) or 0)
                            if "capacity_estimate" in active
                            and active["capacity_estimate"] < len(row)
                            else None
                        ),
                        "status": "proposed",
                        "geocode_confidence": (
                            "source_coordinates"
                            if latitude is not None and longitude is not None
                            else "unverified"
                        ),
                        "source_document_id": source_document_id,
                        "source_url": source_url,
                        "source_page": page_number,
                        "source_table": table_index,
                    }
                    camps.append(record)
                    reasons = []
                    if not current_circle:
                        reasons.append("missing_revenue_circle")
                    if record["coordinates"] is None:
                        reasons.append("missing_or_invalid_coordinates")
                    if reasons:
                        review.append(
                            {
                                "schema_version": 1,
                                "queue_type": "camp_extraction_review",
                                "district": district,
                                "name_raw": name,
                                "source_document_id": source_document_id,
                                "source_page": page_number,
                                "reasons": reasons,
                            }
                        )
    return camps, review
