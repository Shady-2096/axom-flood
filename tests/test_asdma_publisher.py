import hashlib
import json
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from axom_flood import cli
from axom_flood.asdma import publisher
from axom_flood.asdma.client import DownloadedBulletin
from axom_flood.asdma.publisher import (
    ImpactPublicationError,
    publish_impact,
    verify_impact_publication,
)

ROOT = Path(__file__).parents[1]
IST = ZoneInfo("Asia/Kolkata")
NOW = datetime(2026, 7, 29, 12, tzinfo=IST)
RAW_CONTENT: dict[str, bytes] = {}


def _bulletin(report_date: str) -> dict:
    path = next(
        (ROOT / "data" / "processed" / "asdma" / report_date).glob(
            "*-extractor-v7.json"
        )
    )
    document = json.loads(path.read_text())
    raw_path = (
        ROOT
        / "data"
        / "raw"
        / "asdma"
        / report_date
        / f"{document['revision_id']}.pdf"
    )
    RAW_CONTENT[document["revision_id"]] = raw_path.read_bytes()
    return document


def _revision(document: dict, label: str, *, fetched_at: str | None = None) -> dict:
    updated = deepcopy(document)
    raw_content = f"%PDF-test-revision-{label}".encode()
    revision_id = hashlib.sha256(raw_content).hexdigest()
    RAW_CONTENT[revision_id] = raw_content
    updated["revision_id"] = revision_id
    updated["artifact_id"] = (
        f"{revision_id}-extractor-v{updated['extractor_version']}"
    )
    updated["source"]["sha256"] = revision_id
    if fetched_at is not None:
        updated["source"]["fetched_at"] = fetched_at
    for references in updated["field_provenance"].values():
        for reference in references:
            reference["source_revision_sha256"] = revision_id
    for collection in ("infrastructure", "relief_material_notes"):
        for record in updated[collection]:
            for reference in record["provenance"]:
                reference["source_revision_sha256"] = revision_id
    return updated


def _write_bulletin(tmp_path: Path, document: dict, name: str = "bulletin.json") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(document))
    return path


def _publish(tmp_path: Path, document: dict, **kwargs) -> dict:
    raw_path = (
        tmp_path
        / "data"
        / "raw"
        / "asdma"
        / document["report_date"]
        / f"{document['revision_id']}.pdf"
    )
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_bytes(RAW_CONTENT[document["revision_id"]])
    return publish_impact(
        _write_bulletin(tmp_path, document),
        data_dir=tmp_path / "data",
        static_data_dir=tmp_path / "static" / "data",
        now=NOW,
        **kwargs,
    )


def _pointer(tmp_path: Path) -> dict:
    return json.loads(
        (
            tmp_path
            / "data"
            / "processed"
            / "asdma-impact"
            / "impact-current.json"
        ).read_text()
    )


def test_valid_revision_publishes_immutable_impact_and_current_pointer(
    tmp_path: Path,
) -> None:
    bulletin = _bulletin("2026-07-27")

    result = _publish(tmp_path, bulletin)

    assert result["state"] == "validated"
    assert result["profile"] == "impact-v1"
    assert result["pointer_updated"] is True
    assert result["warnings"] == []
    pointer = _pointer(tmp_path)
    assert pointer["revision_id"] == bulletin["revision_id"]
    assert pointer["publication_state"] == "validated"
    impact = json.loads((tmp_path / "static" / pointer["impact_url"]).read_text())
    assert impact["revision_id"] == bulletin["revision_id"]
    assert impact["publication"]["state"] == "validated"
    assert impact["state_summary"]["affected_population"] == 445_495
    assert impact["source"]["artifact_url"] == pointer["source_artifact_url"]
    assert (
        tmp_path / "static" / pointer["source_artifact_url"]
    ).read_bytes() == RAW_CONTENT[bulletin["revision_id"]]
    history = json.loads(
        (tmp_path / "static" / "data" / "impact-history.json").read_text()
    )
    assert history["reports"][0]["revision_id"] == bulletin["revision_id"]
    assert history["reports"][0]["impact_url"] == pointer["impact_url"]
    status = json.loads(
        (tmp_path / "static" / "data" / "impact-status.json").read_text()
    )
    assert status["latest_attempt"]["state"] == "validated"
    assert status["current_valid"]["revision_id"] == bulletin["revision_id"]


def test_approved_source_mismatch_uses_partial_profile_and_withholds_road_details(
    tmp_path: Path,
) -> None:
    bulletin = _bulletin("2026-07-26")

    result = _publish(tmp_path, bulletin)

    assert result["state"] == "validated_partial"
    assert result["profile"] == "impact-v1-infrastructure-count-only"
    assert result["warnings"] == ["infrastructure_source_reconciliation"]
    pointer = _pointer(tmp_path)
    impact = json.loads((tmp_path / "static" / pointer["impact_url"]).read_text())
    assert impact["state_summary"]["infrastructure_incidents"]["road"] == 105
    assert impact["state_summary"]["infrastructure_records_extracted"]["road"] == 97
    assert not any(
        record["incident_type"] == "road" for record in impact["infrastructure"]
    )
    assert "infrastructure_except:road" in impact["publication"]["allowed_fields"]


@pytest.mark.parametrize(
    ("mutation", "expected_failure"),
    [
        (
            lambda document: document["summary"].__setitem__(
                "affected_population",
                document["summary"]["affected_population"] + 1,
            ),
            "district_arithmetic",
        ),
        (
            lambda document: document["summary"].pop("livestock_affected"),
            "bulletin_schema",
        ),
    ],
)
def test_corruption_and_layout_drift_are_quarantined_without_advancing_pointer(
    tmp_path: Path,
    mutation,
    expected_failure: str,
) -> None:
    valid = _bulletin("2026-07-27")
    _publish(tmp_path, valid)
    original_pointer = _pointer(tmp_path)
    invalid = _revision(valid, expected_failure)
    mutation(invalid)

    result = _publish(tmp_path, invalid)

    assert result["state"] == "quarantined"
    assert result["pointer_updated"] is False
    assert result["impact"] is None
    assert expected_failure in result["failures"]
    assert _pointer(tmp_path) == original_pointer
    status = json.loads(
        (tmp_path / "static" / "data" / "impact-status.json").read_text()
    )
    assert status["latest_attempt"]["state"] == "quarantined"
    assert status["latest_attempt"]["revision_id"] == invalid["revision_id"]
    assert status["current_valid"]["revision_id"] == original_pointer["revision_id"]


def test_pointer_write_failure_leaves_public_pointer_untouched_and_retry_recovers(
    tmp_path: Path,
) -> None:
    bulletin = _bulletin("2026-07-27")

    def fail_before_pointer() -> None:
        raise OSError("simulated pointer failure")

    with pytest.raises(OSError, match="simulated pointer failure"):
        _publish(tmp_path, bulletin, before_pointer_update=fail_before_pointer)

    assert not (
        tmp_path / "static" / "data" / "impact-current.json"
    ).exists()
    assert list(
        (tmp_path / "data" / "processed" / "asdma-impact").glob("impact-*.json")
    )

    result = _publish(tmp_path, bulletin)
    assert result["pointer_updated"] is True
    assert _pointer(tmp_path)["revision_id"] == bulletin["revision_id"]


def test_artifact_copy_failure_cannot_create_pointer_and_retry_repairs_it(
    tmp_path: Path,
    monkeypatch,
) -> None:
    bulletin = _bulletin("2026-07-27")
    real_write = publisher._write_immutable

    def fail_public_impact(path: Path, content: bytes) -> None:
        if path.parent == tmp_path / "static" / "data" and path.name.startswith(
            "impact-"
        ):
            raise OSError("simulated public artifact failure")
        real_write(path, content)

    monkeypatch.setattr(publisher, "_write_immutable", fail_public_impact)
    with pytest.raises(OSError, match="simulated public artifact failure"):
        _publish(tmp_path, bulletin)
    assert not (
        tmp_path / "static" / "data" / "impact-current.json"
    ).exists()

    monkeypatch.setattr(publisher, "_write_immutable", real_write)
    result = _publish(tmp_path, bulletin)
    assert result["pointer_updated"] is True
    assert (tmp_path / "static" / "data" / "impact-current.json").exists()


def test_historical_and_superseded_revisions_never_regress_current_pointer(
    tmp_path: Path,
) -> None:
    historical = _bulletin("2026-07-25")
    historical_result = _publish(tmp_path, historical)
    assert historical_result["state"] == "historical"
    assert historical_result["pointer_updated"] is False

    base = _bulletin("2026-07-27")
    newer = _revision(base, "newer", fetched_at="2026-07-28T03:00:00+05:30")
    older = _revision(base, "older", fetched_at="2026-07-28T02:00:00+05:30")
    newer_result = _publish(tmp_path, newer)
    older_result = _publish(tmp_path, older)

    assert newer_result["state"] == "validated"
    assert older_result["state"] == "superseded"
    assert older_result["pointer_updated"] is False
    assert _pointer(tmp_path)["revision_id"] == newer["revision_id"]

    partial_history = _bulletin("2026-07-26")
    partial_history_result = _publish(tmp_path, partial_history)
    assert partial_history_result["state"] == "historical"
    assert partial_history_result["profile"] == "impact-v1-infrastructure-count-only"
    historical_impact = json.loads(Path(partial_history_result["impact"]).read_text())
    assert "infrastructure_except:road" in historical_impact["publication"]["allowed_fields"]
    assert not any(
        record["incident_type"] == "road"
        for record in historical_impact["infrastructure"]
    )


def test_reprocessing_existing_validation_cannot_restore_an_older_pointer(
    tmp_path: Path,
) -> None:
    older = _bulletin("2026-07-26")
    newer = _bulletin("2026-07-27")
    _publish(tmp_path, older)
    _publish(tmp_path, newer)

    result = _publish(tmp_path, older)

    assert result["pointer_updated"] is False
    assert _pointer(tmp_path)["revision_id"] == newer["revision_id"]


def test_unchanged_revision_is_a_content_idempotent_no_op(tmp_path: Path) -> None:
    bulletin = _bulletin("2026-07-27")
    first = _publish(tmp_path, bulletin)
    pointer_bytes = (
        tmp_path / "static" / "data" / "impact-current.json"
    ).read_bytes()

    second = _publish(tmp_path, bulletin)

    assert first["pointer_updated"] is True
    assert second["pointer_updated"] is False
    assert (
        tmp_path / "static" / "data" / "impact-current.json"
    ).read_bytes() == pointer_bytes


def test_phase_c_outputs_match_their_versioned_schemas(tmp_path: Path) -> None:
    result = _publish(tmp_path, _bulletin("2026-07-27"))
    paths_and_schemas = [
        (
            Path(result["validation"]),
            ROOT / "schemas" / "asdma-impact-validation.schema.json",
        ),
        (
            Path(result["impact"]),
            ROOT / "schemas" / "asdma-impact.schema.json",
        ),
        (
            tmp_path
            / "data"
            / "processed"
            / "asdma-impact"
            / "impact-current.json",
            ROOT / "schemas" / "asdma-impact-pointer.schema.json",
        ),
        (
            tmp_path
            / "data"
            / "processed"
            / "asdma-impact"
            / "impact-history.json",
            ROOT / "schemas" / "asdma-impact-history.schema.json",
        ),
        (
            tmp_path
            / "data"
            / "processed"
            / "asdma-impact"
            / "impact-status.json",
            ROOT / "schemas" / "asdma-impact-status.schema.json",
        ),
    ]

    for artifact_path, schema_path in paths_and_schemas:
        validator = Draft202012Validator(
            json.loads(schema_path.read_text()),
            format_checker=FormatChecker(),
        )
        validator.validate(json.loads(artifact_path.read_text()))


def test_impact_schema_rejects_unknown_fields_and_wrong_public_types(
    tmp_path: Path,
) -> None:
    result = _publish(tmp_path, _bulletin("2026-07-27"))
    impact = json.loads(Path(result["impact"]).read_text())
    impact["state_summary"]["invented_metric"] = "not official"
    impact["districts"][0]["affected_population"] = "many"
    impact["rescue"]["boats_deployed"] = "67"
    validator = Draft202012Validator(
        json.loads((ROOT / "schemas" / "asdma-impact.schema.json").read_text()),
        format_checker=FormatChecker(),
    )

    errors = list(validator.iter_errors(impact))

    assert len(errors) >= 3


def test_network_failure_cannot_touch_an_existing_pointer(
    tmp_path: Path,
    monkeypatch,
) -> None:
    data_dir = tmp_path / "data"
    pointer_path = data_dir / "processed" / "asdma-impact" / "impact-current.json"
    pointer_path.parent.mkdir(parents=True)
    pointer_path.write_text('{"revision_id":"safe"}\n')
    before = pointer_path.read_bytes()

    def fail_fetch(*args, **kwargs):
        raise OSError("network unavailable")

    monkeypatch.setattr(cli, "fetch_bulletin", fail_fetch)
    with pytest.raises(OSError, match="network unavailable"):
        cli._fetch_one(
            datetime(2026, 7, 28, tzinfo=IST).date(),
            data_dir,
            tmp_path / "static" / "data",
            timeout_seconds=1,
            max_attempts=1,
            retry_backoff_seconds=0,
        )

    assert pointer_path.read_bytes() == before


def test_parser_drift_preserves_raw_source_and_writes_quarantine_record(
    tmp_path: Path,
    monkeypatch,
) -> None:
    report_date = datetime(2026, 7, 28, tzinfo=IST).date()
    download = DownloadedBulletin(
        requested_date=report_date,
        fetched_at=NOW,
        source_url="https://sdrf.assam.gov.in/dfr/download",
        content=b"%PDF-structurally-unfamiliar",
        content_type="application/pdf",
    )
    monkeypatch.setattr(cli, "fetch_bulletin", lambda *args, **kwargs: download)

    result = cli._fetch_one(
        report_date,
        tmp_path / "data",
        tmp_path / "static" / "data",
        timeout_seconds=1,
        max_attempts=1,
        retry_backoff_seconds=0,
    )

    publication = result["impact_publication"]
    assert publication["state"] == "quarantined"
    assert publication["failures"] == ["source_structure"]
    assert publication["pointer_updated"] is False
    raw_paths = list(
        (tmp_path / "data" / "raw" / "asdma" / "2026-07-28").glob("*.pdf")
    )
    assert len(raw_paths) == 1
    validation = json.loads(Path(publication["validation"]).read_text())
    schema = json.loads(
        (ROOT / "schemas" / "asdma-impact-validation.schema.json").read_text()
    )
    Draft202012Validator(
        schema,
        format_checker=FormatChecker(),
    ).validate(validation)


def test_cli_marks_quarantine_as_visible_failure(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setattr(
        cli,
        "publish_impact",
        lambda *args, **kwargs: {
            "state": "quarantined",
            "revision_id": "a" * 64,
            "pointer_updated": False,
        },
    )
    args = cli.build_parser().parse_args(
        [
            "asdma",
            "publish",
            "--bulletin",
            str(tmp_path / "candidate.json"),
            "--data-dir",
            str(tmp_path / "data"),
            "--static-data-dir",
            str(tmp_path / "static" / "data"),
        ]
    )

    assert cli._run_asdma(args) == 1
    assert "current impact pointer is unchanged" in capsys.readouterr().err
    status_path = next((tmp_path / "data" / "run-status" / "asdma").glob("*.json"))
    assert json.loads(status_path.read_text())["status"] == "quarantined"


def test_production_verifier_checks_pointer_and_lazy_artifact() -> None:
    revision_id = "a" * 64
    expected = {
        "revision_id": revision_id,
        "report_date": "2026-07-27",
        "publication_state": "validated",
        "impact_url": "data/impact-test.json",
    }
    responses = {
        "https://example.test/data/impact-current.json": expected,
        "https://example.test/data/impact-test.json": {
            "revision_id": revision_id,
            "publication": {"state": "validated"},
        },
    }

    result = verify_impact_publication(
        base_url="https://example.test",
        expected_pointer=expected,
        fetch_json=responses.__getitem__,
    )

    assert result["revision_id"] == revision_id


def test_production_verifier_rejects_the_wrong_revision() -> None:
    expected = {
        "revision_id": "a" * 64,
        "report_date": "2026-07-27",
        "publication_state": "validated",
        "impact_url": "data/impact-test.json",
    }

    with pytest.raises(ImpactPublicationError, match="revision_id mismatch"):
        verify_impact_publication(
            base_url="https://example.test",
            expected_pointer=expected,
            fetch_json=lambda _: {**expected, "revision_id": "b" * 64},
        )
