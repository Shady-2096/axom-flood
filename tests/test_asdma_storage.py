import hashlib
import json
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from axom_flood.asdma import storage
from axom_flood.asdma.client import DownloadedBulletin
from axom_flood.asdma.parser import BulletinParseError


def test_persist_is_idempotent_and_series_is_append_only(tmp_path, monkeypatch) -> None:
    content = b"%PDF-fixture"
    digest = hashlib.sha256(content).hexdigest()
    parsed = {
        "schema_version": 1,
        "extractor_version": 1,
        "report_date": "2026-07-25",
        "rivers_above_danger_level": [],
        "rivers_above_highest_flood_level": [],
        "affected_district_names": ["Sivasagar"],
        "summary": {
            "affected_districts": 1,
            "affected_revenue_circles": 1,
            "affected_villages": 2,
            "affected_population": 3,
            "crop_area_submerged_hectares": 4,
            "relief_camps_open": 5,
            "relief_distribution_centres_open": 6,
            "relief_camp_occupants": 7,
            "confirmed_deaths": 0,
        },
        "districts": [{"district": "Sivasagar"}],
        "field_provenance": {
            "summary.affected_population": [
                {"page": 1, "table": 1, "row": 12, "section": "population"}
            ]
        },
        "relief_material_notes": [],
        "infrastructure": [],
        "extraction_warnings": [],
    }
    monkeypatch.setattr(storage, "parse_bulletin", lambda _: parsed)
    download = DownloadedBulletin(
        requested_date=date(2026, 7, 25),
        fetched_at=datetime(2026, 7, 26, 10, tzinfo=ZoneInfo("Asia/Kolkata")),
        source_url="https://sdrf.assam.gov.in/dfr/download",
        content=content,
        content_type="application/pdf",
    )

    first = storage.persist_bulletin(download, data_dir=tmp_path)
    fetched_again = DownloadedBulletin(
        requested_date=download.requested_date,
        fetched_at=download.fetched_at + timedelta(hours=1),
        source_url=download.source_url,
        content=download.content,
        content_type=download.content_type,
    )
    second = storage.persist_bulletin(fetched_again, data_dir=tmp_path)

    assert first == second
    assert first["revision_id"] == digest
    assert first["artifact_id"] == f"{digest}-extractor-v1"
    lines = (tmp_path / "series" / "asdma_flood_summary.jsonl").read_text().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["artifact_id"] == f"{digest}-extractor-v1"
    persisted = json.loads(
        (
            tmp_path
            / "processed"
            / "asdma"
            / "2026-07-25"
            / f"{digest}-extractor-v1.json"
        ).read_text()
    )
    assert persisted["field_provenance"]["summary.affected_population"] == [
        {
            "source_revision_sha256": digest,
            "report_date": "2026-07-25",
            "extractor_version": 1,
            "page": 1,
            "table": 1,
            "row": 12,
            "section": "population",
        }
    ]


def test_raw_revision_is_preserved_when_layout_drift_breaks_parsing(
    tmp_path,
    monkeypatch,
) -> None:
    content = b"%PDF-layout-drift"
    digest = hashlib.sha256(content).hexdigest()
    download = DownloadedBulletin(
        requested_date=date(2026, 7, 28),
        fetched_at=datetime(2026, 7, 29, 10, tzinfo=ZoneInfo("Asia/Kolkata")),
        source_url="https://sdrf.assam.gov.in/dfr/download",
        content=content,
        content_type="application/pdf",
    )
    monkeypatch.setattr(
        storage,
        "parse_bulletin",
        lambda _: (_ for _ in ()).throw(BulletinParseError("unknown layout")),
    )

    with pytest.raises(BulletinParseError, match="unknown layout"):
        storage.persist_bulletin(download, data_dir=tmp_path)

    raw_dir = tmp_path / "raw" / "asdma" / "2026-07-28"
    assert (raw_dir / f"{digest}.pdf").read_bytes() == content
    metadata = json.loads((raw_dir / f"{digest}.metadata.json").read_text())
    assert metadata["sha256"] == digest


def test_immutable_write_failure_never_exposes_a_partial_final_file(
    tmp_path,
    monkeypatch,
) -> None:
    path = tmp_path / "immutable.json"
    real_link = storage.os.link

    def fail_publish(*args, **kwargs):
        raise OSError("simulated atomic publication failure")

    monkeypatch.setattr(storage.os, "link", fail_publish)
    with pytest.raises(OSError, match="simulated atomic publication failure"):
        storage._write_immutable(path, b'{"complete":true}\n')

    assert not path.exists()
    assert not list(tmp_path.glob(".*.tmp"))

    monkeypatch.setattr(storage.os, "link", real_link)
    storage._write_immutable(path, b'{"complete":true}\n')
    assert path.read_bytes() == b'{"complete":true}\n'
