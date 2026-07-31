"""End-to-end district document discovery, preservation, and camp extraction."""

from __future__ import annotations

import csv
import hashlib
from datetime import datetime
from io import StringIO
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from ..asdma.storage import _json_bytes, _write_immutable
from .discovery import USER_AGENT, discover_district_sources, load_district_registry
from .parser import EXTRACTOR_VERSION, parse_dedicated_camp_pdf


def _csv_bytes(records: list[dict[str, Any]]) -> bytes:
    fields = [
        "district",
        "revenue_circle",
        "name_raw",
        "village",
        "longitude",
        "latitude",
        "contact_phone",
        "capacity_estimate",
        "status",
        "geocode_confidence",
        "source_document_id",
        "source_url",
        "source_page",
    ]
    output = StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for record in records:
        coordinates = record.get("coordinates") or [None, None]
        writer.writerow(
            {
                **{key: record.get(key) for key in fields},
                "longitude": coordinates[0],
                "latitude": coordinates[1],
            }
        )
    return output.getvalue().encode()


def run_camp_pipeline(
    *,
    registry_path: Path,
    data_dir: Path,
    timeout_seconds: float = 30,
) -> dict[str, Any]:
    registry = load_district_registry(registry_path)
    with httpx.Client(
        follow_redirects=True,
        timeout=timeout_seconds,
        headers={"User-Agent": USER_AGENT},
    ) as client:
        discovery = discover_district_sources(registry, client=client)
        discovery_digest = hashlib.sha256(_json_bytes(discovery)).hexdigest()
        discovery_path = data_dir / "discovery" / "camps" / f"{discovery_digest}.json"
        _write_immutable(discovery_path, _json_bytes(discovery))

        camps: list[dict[str, Any]] = []
        review: list[dict[str, Any]] = []
        documents_downloaded = 0
        for district in discovery["districts"]:
            for document in district["documents"]:
                try:
                    response = client.get(document["url"])
                    response.raise_for_status()
                    content = response.content
                    if not content.startswith(b"%PDF"):
                        raise ValueError("document response is not a PDF")
                    digest = hashlib.sha256(content).hexdigest()
                    raw_path = (
                        data_dir
                        / "raw"
                        / "district-camps"
                        / district["slug"]
                        / f"{digest}.pdf"
                    )
                    _write_immutable(raw_path, content)
                    documents_downloaded += 1
                    if document["document_type"] != "dedicated_camp_list":
                        review.append(
                            {
                                "schema_version": 1,
                                "queue_type": "document_parser_needed",
                                "district": district["district"],
                                "title": document["title"],
                                "source_url": document["url"],
                                "source_document_id": digest,
                                "reason": "contingency_plan_requires_document_specific_parser",
                            }
                        )
                        continue
                    parsed, parsed_review = parse_dedicated_camp_pdf(
                        content,
                        district=district["district"],
                        source_document_id=digest,
                        source_url=document["url"],
                    )
                    camps.extend(parsed)
                    review.extend(parsed_review)
                except Exception as exc:
                    review.append(
                        {
                            "schema_version": 1,
                            "queue_type": "document_download_or_parse_failure",
                            "district": district["district"],
                            "title": document["title"],
                            "source_url": document["url"],
                            "reason": f"{type(exc).__name__}: {exc}",
                        }
                    )

    artifact = {
        "schema_version": 1,
        "extractor_version": EXTRACTOR_VERSION,
        "generated_at": datetime.now(ZoneInfo("Asia/Kolkata")).isoformat(),
        "district_registry_count": len(registry["districts"]),
        "discovery_id": discovery_digest,
        "camp_count": len(camps),
        "camps": camps,
    }
    artifact_digest = hashlib.sha256(_json_bytes(artifact)).hexdigest()
    output_dir = data_dir / "processed" / "district-camps"
    json_path = output_dir / f"{artifact_digest}.json"
    csv_path = output_dir / f"{artifact_digest}.csv"
    review_path = data_dir / "review" / "district-camps" / f"{artifact_digest}.json"
    _write_immutable(json_path, _json_bytes(artifact))
    _write_immutable(csv_path, _csv_bytes(camps))
    _write_immutable(
        review_path,
        _json_bytes(
            {
                "schema_version": 1,
                "artifact_id": artifact_digest,
                "review_count": len(review),
                "items": review,
            }
        ),
    )
    return {
        "artifact_id": artifact_digest,
        "districts_crawled": len(registry["districts"]),
        "documents_downloaded": documents_downloaded,
        "camps_extracted": len(camps),
        "review_items": len(review),
        "json": str(json_path),
        "csv": str(csv_path),
        "review_queue": str(review_path),
        "discovery": str(discovery_path),
    }
