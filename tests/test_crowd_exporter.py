"""The path from a reviewed database row to a published crowd artifact.

Before this existed, reports could arrive from the website and the bots, land
in Postgres, and stop there: nothing carried them into the artifacts the site
actually reads.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from axom_flood.crowd.exporter import (
    ExportError,
    ExportNotConfigured,
    SupabaseReportSource,
    export_reports,
    publishable,
    submission_from_row,
)
from axom_flood.crowd.pipeline import publish_open_dataset

SALT = b"export-test-salt"
MONTH = "2026-07"
NOW = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)
SINCE = NOW - timedelta(days=1)
UNTIL = NOW + timedelta(minutes=1)
LOCALITIES = Path("config/assam-localities.json")


def row(**overrides: Any) -> dict[str, Any]:
    base = {
        "report_id": "11111111-2222-3333-4444-555555555555",
        # Inside the aggregate's one-hour window, so a quorum can form.
        "observed_at": datetime(2026, 7, 30, 11, 30, tzinfo=UTC),
        "locality_id": "karbi-anglong-silonijan",
        "depth_class": "knee",
        "reporter_hash": "a" * 64,
        "verification_state": "pending",
        "longitude": 93.612,
        "latitude": 26.107,
    }
    base.update(overrides)
    return base


class FakeSource:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.calls: list[tuple[datetime, datetime]] = []

    def export_report_candidates(self, since: datetime, until: datetime):
        self.calls.append((since, until))
        return list(self.rows)


def test_row_becomes_a_submission_the_pipeline_already_accepts() -> None:
    submission = submission_from_row(row())

    # Only allow-listed keys, so the pipeline's PII seal keeps working.
    from axom_flood.crowd.pipeline import CROWD_SUBMISSION_KEYS

    assert set(submission) <= CROWD_SUBMISSION_KEYS
    assert submission["depth_class"] == "knee"
    assert submission["locality_id"] == "karbi-anglong-silonijan"
    # The database HMAC is what gets salted again, not a raw sender identifier.
    assert submission["device_token"] == "a" * 64


def test_moderation_metadata_never_reaches_the_submission() -> None:
    submission = submission_from_row(row(verification_state="corroborated"))
    assert "verification_state" not in submission
    assert "reporter_hash" not in submission


def test_disputed_and_rejected_reports_are_withheld() -> None:
    assert publishable(row(verification_state="pending")) is True
    assert publishable(row(verification_state="corroborated")) is True
    assert publishable(row(verification_state="disputed")) is False
    assert publishable(row(verification_state="rejected")) is False


def test_an_unknown_verification_state_stops_the_export() -> None:
    # A state added to the database later must not be published by default.
    with pytest.raises(ExportError, match="unknown verification_state"):
        publishable(row(verification_state="under_appeal"))


def test_export_ingests_publishable_rows_and_counts_the_rest(tmp_path: Path) -> None:
    source = FakeSource(
        [
            row(report_id="aaaaaaaa-0000-0000-0000-000000000001"),
            row(
                report_id="aaaaaaaa-0000-0000-0000-000000000002",
                depth_class="waist_plus",
                verification_state="corroborated",
            ),
            row(
                report_id="aaaaaaaa-0000-0000-0000-000000000003",
                verification_state="rejected",
            ),
        ]
    )

    result = export_reports(
        source,
        since=SINCE,
        until=UNTIL,
        data_dir=tmp_path / "data",
        salt=SALT,
        month=MONTH,
        now=NOW,
    )

    assert result["rows_considered"] == 3
    assert result["reports_appended"] == 2
    assert result["reports_withheld"] == 1
    assert source.calls == [(SINCE, UNTIL)]


def test_rerunning_an_overlapping_window_does_not_duplicate(tmp_path: Path) -> None:
    source = FakeSource([row()])
    data_dir = tmp_path / "data"
    kwargs = dict(since=SINCE, until=UNTIL, data_dir=data_dir, salt=SALT, month=MONTH, now=NOW)

    first = export_reports(source, **kwargs)
    second = export_reports(source, **kwargs)

    assert first["reports_appended"] == 1
    assert second["reports_appended"] == 0
    assert second["reports_already_present"] == 1


def test_exported_reports_reach_the_public_artifact_as_aggregates(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    # Three separate reporters in one place, which is what a quorum needs.
    source = FakeSource(
        [
            row(
                report_id=f"aaaaaaaa-0000-0000-0000-00000000000{index}",
                reporter_hash=str(index) * 64,
            )
            for index in (1, 2, 3)
        ]
    )
    export_reports(
        source,
        since=SINCE,
        until=UNTIL,
        data_dir=data_dir,
        salt=SALT,
        month=MONTH,
        now=NOW,
    )

    published = publish_open_dataset(
        data_dir=data_dir,
        localities_path=LOCALITIES,
        now=NOW,
    )
    artifact = json.loads(Path(published["json"]).read_text())

    assert artifact["privacy_scope"] == "aggregate_only"
    assert artifact["report_count_total"] == 3
    assert artifact["aggregate_statements"], "three reporters in one place is a quorum"

    # Nothing that identifies a device or a database row may appear.
    audit = json.dumps(artifact, sort_keys=True)
    for private in ("reporter_hash", "device_hash", "report_id", "verification_state"):
        assert f'"{private}"' not in audit
    assert "a" * 64 not in audit


def test_a_row_without_a_depth_class_fails_loudly(tmp_path: Path) -> None:
    with pytest.raises(ExportError, match="no depth_class"):
        submission_from_row(row(depth_class=None))


def test_a_naive_timestamp_is_refused() -> None:
    with pytest.raises(ExportError, match="must carry a timezone"):
        submission_from_row(row(observed_at=datetime(2026, 7, 30, 11, 30)))


def test_a_short_reporter_hash_is_refused() -> None:
    with pytest.raises(ExportError, match="64-character"):
        submission_from_row(row(reporter_hash="tooshort"))


def test_without_credentials_the_export_refuses_instead_of_pretending() -> None:
    # No database is configured yet, so the honest outcome is a clear refusal
    # rather than an empty run that looks like "no reports today".
    with pytest.raises(ExportNotConfigured, match="SUPABASE_URL"):
        SupabaseReportSource.from_env({})
    with pytest.raises(ExportNotConfigured, match="SUPABASE_URL"):
        SupabaseReportSource.from_env({"SUPABASE_URL": "https://example.invalid"})


def test_a_backwards_window_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ExportError, match="must end after it starts"):
        export_reports(
            FakeSource([]),
            since=UNTIL,
            until=SINCE,
            data_dir=tmp_path / "data",
            salt=SALT,
            month=MONTH,
            now=NOW,
        )
