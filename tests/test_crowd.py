"""Phase 2 privacy and display-rule tests.

Recorded shapes only &mdash; no network. These tests are the proof of the
privacy guarantees the plan calls hard requirements, and of the display
rules that prevent a single report from being shown as fact.
"""

import json
import math
import re
import secrets
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from axom_flood.crowd import (
    PrivacyError,
    assert_no_pii,
    device_hash,
    ingest_crowd_inbox,
    ingest_crowd_submission,
    ingest_high_water_mark,
    publish_open_dataset,
    round_coordinate,
    serialise_for_audit,
)
from axom_flood.crowd.aggregate import (
    aggregate_statements,
    display_confidence,
    flag_contradictions,
    is_visible,
)
from axom_flood.crowd.pipeline import build_crowd_report, build_high_water_mark
from axom_flood.crowd.privacy import _UNSCANNED_KEYS

IST = ZoneInfo("Asia/Kolkata")
NOW = datetime(2026, 7, 27, 14, 31, tzinfo=IST)
SALT = secrets.token_bytes(32)
MONTH = "2026-07"

PLAN_REPORT_KEYS = {
    "schema_version",
    "report_id",
    "submitted_at",
    "location",
    "location_precision_m",
    "depth_class",
    "locality_id",
    "source",
    "device_hash",
    "flags",
}
PLAN_HWM_KEYS = {"location", "year", "depth_cm", "reference_en", "confidence"}
# schema_version is added per the repo-wide rule that every artifact carries
# one (schemas/README.md); hwm_id and submitted_at are the provenance pair so
# the recalled body stays in the plan's exact shape.
HWM_PROVENANCE_KEYS = {"schema_version", "hwm_id", "submitted_at"}


def submission(**overrides):
    base = {
        "latitude": 26.9123456789,
        "longitude": 94.6801234567,
        "depth_class": "knee",
        "device_token": "client-uuid-1234567890",
        "source": "app",
        "submitted_at": NOW.isoformat(),
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Coordinate rounding
# ---------------------------------------------------------------------------


def test_round_coordinate_stores_only_three_decimals() -> None:
    lat, lon = round_coordinate(26.9123456789, 94.6801234567)
    assert lat == round(26.9123456789, 3)
    assert lon == round(94.6801234567, 3)
    # The full-precision coordinate cannot be recovered from what is stored.
    assert lat != 26.9123456789
    assert lon != 94.6801234567


def test_stored_grid_resolution_is_at_least_50m_across_india() -> None:
    """The stored three-decimal grid must be no finer than 50 m anywhere."""
    metres_per_deg = 111_320.0
    step = 10 ** -3
    for latitude in (8.0, 22.0, 26.6, 35.0):
        lat_resolution = step * metres_per_deg
        lon_resolution = step * metres_per_deg * math.cos(math.radians(latitude))
        assert lat_resolution >= 50, f"lat grid finer than 50 m at {latitude} N"
        assert lon_resolution >= 50, f"lon grid finer than 50 m at {latitude} N"


def test_round_coordinate_rejects_out_of_range() -> None:
    with pytest.raises(ValueError):
        round_coordinate(91.0, 0.0)
    with pytest.raises(ValueError):
        round_coordinate(0.0, 181.0)


# ---------------------------------------------------------------------------
# device_hash
# ---------------------------------------------------------------------------


def test_device_hash_is_stable_within_month() -> None:
    same_token = "client-uuid"
    assert device_hash(same_token, SALT, MONTH) == device_hash(same_token, SALT, MONTH)


def test_device_hash_rotates_with_month_and_salt() -> None:
    token = "client-uuid"
    h_july = device_hash(token, SALT, "2026-07")
    h_august_with_same_salt = device_hash(token, SALT, "2026-08")
    h_august_other_salt = device_hash(token, secrets.token_bytes(32), "2026-08")
    # An observer of the published hashes cannot link the same device across
    # months: both the month string and the salt rotate, so every monthly
    # hash differs.
    assert len({h_july, h_august_with_same_salt, h_august_other_salt}) == 3


def test_device_hash_publishes_no_raw_token() -> None:
    token = "client-uuid-plain"
    digest = device_hash(token, SALT, MONTH)
    assert digest != token
    assert token not in digest
    assert len(digest) == 64


def test_device_hash_requires_strong_salt() -> None:
    with pytest.raises(ValueError):
        device_hash("token", b"short", MONTH)


# ---------------------------------------------------------------------------
# The hard privacy test: construct from full-precision input, prove no PII
# ---------------------------------------------------------------------------


def test_crowd_report_stores_only_rounded_anonymous_shape() -> None:
    raw = submission()
    report, banned = build_crowd_report(raw, salt=SALT, month=MONTH, now=NOW)
    # Exactly the plan's field set plus schema_version.
    assert set(report) == PLAN_REPORT_KEYS
    assert report["schema_version"] == 1
    assert report["location_precision_m"] == 50
    # Round-trip: the published coordinate lies on the three-decimal grid.
    lon, lat = report["location"]
    assert lat == round(lat, 3)
    assert lon == round(lon, 3)

    audit = serialise_for_audit(report)
    # The raw full-precision GPS reading appears nowhere in the published
    # record, as a number or as a string.
    for witness in (
        raw["latitude"],
        raw["longitude"],
        str(raw["latitude"]),
        str(raw["longitude"]),
        26.9123456789,
        94.6801234567,
        raw["device_token"],
    ):
        assert str(witness) not in audit

    # The PII scanner must accept the clean record and reject any banned
    # value leaking back in.
    assert_no_pii(report, banned_values=banned)


@pytest.mark.parametrize(
    "pii_key",
    ["name", "phone", "phone_number", "email", "imei", "device_id", "user_id", "account"],
)
def test_report_cannot_carry_a_pii_field_name(pii_key) -> None:
    raw = submission()
    raw[pii_key] = "anything"
    with pytest.raises((PrivacyError, ValueError)):
        build_crowd_report(raw, salt=SALT, month=MONTH, now=NOW)


def test_raw_device_token_never_reaches_the_stored_record() -> None:
    """``device_token`` is the legitimate transient input for duplicate
    detection; only its salted hash is published, never the raw token.
    """
    raw = submission()
    report, _ = build_crowd_report(raw, salt=SALT, month=MONTH, now=NOW)
    assert "device_token" not in report
    assert "device_id" not in report
    audit = serialise_for_audit(report)
    assert raw["device_token"] not in audit


def test_free_text_field_with_an_embedded_phone_is_rejected() -> None:
    payload = {
        "schema_version": 1,
        "hwm_id": "x",
        "submitted_at": NOW.isoformat(),
        "location": [94.68, 26.91],
        "year": 2023,
        "depth_cm": 110,
        "reference_en": "call me at 9876543210 to verify",
        "confidence": "recalled",
    }
    with pytest.raises(PrivacyError):
        assert_no_pii(payload)


def test_device_hash_value_is_not_misread_as_a_phone_number() -> None:
    """A sha256 hex digest can contain ten consecutive decimal digits.

    ``reference_en`` is the only free-text field scanned for phone-number
    patterns; ``device_hash`` is not, so a hash that happens to contain
    ``6789012345`` must not false-trip the scanner.
    """
    raw = submission()
    report, _ = build_crowd_report(raw, salt=SALT, month=MONTH, now=NOW)
    # Assert no PII scan complaint against the clean record.
    assert_no_pii(report)


# ---------------------------------------------------------------------------
# Ingest + raw-source erasure
# ---------------------------------------------------------------------------


def test_ingest_appends_only_rounded_report_and_deletes_the_raw_file(tmp_path):
    data_dir = tmp_path / "data"
    inbox = data_dir / "inbox" / "crowd"
    inbox.mkdir(parents=True)
    raw = submission()
    (inbox / "001.json").write_text(json.dumps(raw))

    summary = ingest_crowd_inbox(inbox=inbox, data_dir=data_dir, now=NOW)
    assert summary["ingested"] == 1
    assert summary["raw_files_deleted"] == 1
    # The raw file is gone, so the full-precision GPS and raw device token
    # are not persisted anywhere.
    assert not (inbox / "001.json").exists()

    series = (data_dir / "series" / "crowd_reports.jsonl").read_text().splitlines()
    assert len(series) == 1
    stored = json.loads(series[0])
    audit = json.dumps(stored, sort_keys=True)
    assert "26.9123456789" not in audit
    assert "94.6801234567" not in audit
    assert "client-uuid" not in audit
    assert set(stored) == PLAN_REPORT_KEYS


def test_ingest_deduplicates_by_report_id(tmp_path):
    data_dir = tmp_path / "data"
    inbox = data_dir / "inbox" / "crowd"
    inbox.mkdir(parents=True)
    raw = submission(report_id="11111111-2222-3333-4444-555555555555")
    (inbox / "a.json").write_text(json.dumps(raw))
    (inbox / "b.json").write_text(json.dumps(raw))

    summary = ingest_crowd_inbox(inbox=inbox, data_dir=data_dir, now=NOW)
    assert summary["ingested"] == 2
    assert summary["duplicates"] == 1
    series = (data_dir / "series" / "crowd_reports.jsonl").read_text().splitlines()
    assert len(series) == 1


def test_keep_raw_flag_preserves_submissions(tmp_path):
    data_dir = tmp_path / "data"
    inbox = data_dir / "inbox" / "crowd"
    inbox.mkdir(parents=True)
    (inbox / "001.json").write_text(json.dumps(submission()))

    summary = ingest_crowd_inbox(inbox=inbox, data_dir=data_dir, now=NOW, delete_raw=False)
    assert summary["raw_files_deleted"] == 0
    assert (inbox / "001.json").exists()


# ---------------------------------------------------------------------------
# High-water marks: stored separately, never mixed with live reports
# ---------------------------------------------------------------------------


def test_high_water_mark_uses_the_plans_exact_field_shape() -> None:
    raw = {
        "latitude": 26.9123456789,
        "longitude": 94.6801234567,
        "year": 2023,
        "depth_cm": 110,
        "reference_en": "up to the window sill",
        "confidence": "recalled",
    }
    record, banned = build_high_water_mark(raw, now=NOW)
    # The body of the recalled record is exactly the plan's field set.
    body = {k: record[k] for k in PLAN_HWM_KEYS}
    assert set(body) == PLAN_HWM_KEYS
    # The container adds provenance only.
    assert set(record) == PLAN_HWM_KEYS | HWM_PROVENANCE_KEYS
    assert body["reference_en"] == "up to the window sill"
    assert body["confidence"] == "recalled"
    # And it carries no full-precision coordinate.
    audit = serialise_for_audit(record)
    for witness in (raw["latitude"], raw["longitude"], str(raw["latitude"]), str(raw["longitude"])):
        assert str(witness) not in audit
    assert_no_pii(record, banned_values=banned)


def test_high_water_marks_are_stored_separately_from_live_reports(tmp_path):
    data_dir = tmp_path / "data"
    series_crowd = data_dir / "series" / "crowd_reports.jsonl"
    series_hwm = data_dir / "series" / "high_water_marks.jsonl"

    ingest_crowd_submission(
        submission(),
        data_dir=data_dir,
        salt=SALT,
        month=MONTH,
        now=NOW,
    )
    ingest_high_water_mark(
        {
            "latitude": 26.9123456789,
            "longitude": 94.6801234567,
            "year": 2023,
            "depth_cm": 110,
            "reference_en": "up to the window sill",
            "confidence": "recalled",
        },
        data_dir=data_dir,
        now=NOW,
    )
    assert series_crowd.exists() and len(series_crowd.read_text().splitlines()) == 1
    assert series_hwm.exists() and len(series_hwm.read_text().splitlines()) == 1
    # No HWM record reaches the live crowd series.
    assert "up to the window sill" not in series_crowd.read_text()


# ---------------------------------------------------------------------------
# Display rules
# ---------------------------------------------------------------------------


def _report_at(depth, age_minutes, *, lat=26.912, lon=94.681, place="nazira_town"):
    submitted = NOW - timedelta(minutes=age_minutes)
    return {
        "report_id": f"rid-{depth}-{age_minutes}",
        "submitted_at": submitted.isoformat(),
        "location": [lon, lat],
        "location_precision_m": 50,
        "depth_class": depth,
        "locality_id": place,
        "source": "app",
        "device_hash": "x" * 64,
        "flags": [],
    }


def test_display_confidence_fades_to_zero_over_six_hours() -> None:
    assert display_confidence(_report_at("knee", 0), now=NOW) == pytest.approx(1.0)
    assert display_confidence(_report_at("knee", 180), now=NOW) == pytest.approx(0.5)
    assert display_confidence(_report_at("knee", 360), now=NOW) == pytest.approx(0.0, abs=1e-9)


def test_reports_older_than_12_hours_hidden_during_an_active_event() -> None:
    fresh = _report_at("knee", 60)
    old = _report_at("knee", 13 * 60)
    assert is_visible(fresh, now=NOW, active_event=True) is True
    assert is_visible(old, now=NOW, active_event=True) is False
    # Outside an active event nothing is hidden by the 12 h rule.
    assert is_visible(old, now=NOW, active_event=False) is True


def test_single_report_is_never_shown_as_fact() -> None:
    reports = [_report_at("knee", 30)]
    statements = aggregate_statements(reports, now=NOW, localities={})
    assert len(statements) == 1
    assert statements[0]["count"] == 1
    assert statements[0]["quorum"] is False


def test_aggregate_statement_three_people_knee_within_the_hour() -> None:
    reports = [
        _report_at("knee", 5),
        _report_at("knee", 20),
        _report_at("knee", 40),
    ]
    statements = aggregate_statements(
        reports,
        now=NOW,
        localities={"nazira_town": {"revenue_circle": "Nazira"}},
    )
    assert len(statements) == 1
    stmt = statements[0]
    assert stmt["count"] == 3
    assert stmt["depth_class"] == "knee"
    assert stmt["place"] == "Nazira"
    assert stmt["within_hours"] == 1
    assert stmt["quorum"] is True


def test_dry_reports_carry_equal_weight_to_wet_ones() -> None:
    """A dry report is the bound on the water surface in Phase 3 and must
    aggregate exactly the same way a wet report does.
    """
    dry = aggregate_statements([_report_at("dry", 5)], now=NOW, localities={})
    wet = aggregate_statements([_report_at("knee", 5)], now=NOW, localities={})
    assert dry[0]["quorum"] == wet[0]["quorum"] is False


def test_a_contradicting_report_is_flagged_not_deleted() -> None:
    reports = [
        _report_at("dry", 5),
        _report_at("knee", 10),
    ]
    flagged = flag_contradictions(reports)
    assert len(flagged) == 2
    assert all("neighbour_contradiction" in r["flags"] for r in flagged)
    # The reports remain in the set; nothing is dropped.
    assert len(reports) == 2


def test_a_report_that_agrees_with_neighbours_is_not_flagged() -> None:
    reports = [
        _report_at("knee", 5),
        _report_at("knee", 10),
    ]
    assert flag_contradictions(reports) == []


# ---------------------------------------------------------------------------
# Publish open dataset (content-hashed immutable)
# ---------------------------------------------------------------------------


def test_publish_open_dataset_is_content_hashed_and_immutable(tmp_path):
    data_dir = tmp_path / "data"
    for depth, age in (("knee", 5), ("knee", 12), ("dry", 30)):
        ingest_crowd_submission(
            submission(depth_class=depth, submitted_at=(NOW - timedelta(minutes=age)).isoformat()),
            data_dir=data_dir,
            salt=SALT,
            month=MONTH,
            now=NOW,
        )
    result = publish_open_dataset(
        data_dir=data_dir,
        localities_path=Path("config/assam-localities.json"),
        now=NOW,
    )
    path = Path(result["json"])
    artifact = json.loads(path.read_text())
    assert artifact["schema_version"] == 2
    assert artifact["privacy_scope"] == "aggregate_only"
    assert artifact["report_count_total"] == 3
    assert artifact["report_count_visible"] == 3
    audit = json.dumps(artifact, sort_keys=True)
    for private_key in (
        "reports",
        "report_ids",
        "report_id",
        "device_hash",
        "location",
        "display_confidence_by_report_id",
        "source_series",
    ):
        assert f'"{private_key}"' not in audit
    assert all(statement["quorum"] for statement in artifact["aggregate_statements"])
    # The published artifact name is the SHA-256 of its bytes.
    assert path.name == f"{result['artifact_id']}.json"


def test_public_artifact_withholds_single_report_place_and_identity(tmp_path):
    data_dir = tmp_path / "data"
    raw = submission(locality_id="nazira_town")
    ingest_crowd_submission(
        raw,
        data_dir=data_dir,
        salt=SALT,
        month=MONTH,
        now=NOW,
    )

    result = publish_open_dataset(
        data_dir=data_dir,
        localities_path=Path("config/assam-localities.json"),
        now=NOW,
        active_event=False,
    )
    artifact = json.loads(Path(result["json"]).read_text())
    audit = json.dumps(artifact, sort_keys=True)

    assert artifact["aggregate_statements"] == []
    assert artifact["below_quorum_group_count"] == 1
    assert "nazira_town" not in audit
    assert raw["device_token"] not in audit


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def test_cli_crowd_ingest_publishes_open_dataset_and_deletes_raw(tmp_path):
    from axom_flood.cli import _run_crowd, build_parser

    data_dir = tmp_path / "data"
    inbox = data_dir / "inbox" / "crowd"
    inbox.mkdir(parents=True)
    (inbox / "001.json").write_text(json.dumps(submission()))

    parser = build_parser()
    args = parser.parse_args(
        [
            "crowd",
            "ingest",
            "--inbox",
            str(inbox),
            "--data-dir",
            str(data_dir),
            "--localities",
            "config/assam-localities.json",
        ]
    )
    rc = _run_crowd(args)
    assert rc == 0
    assert not (inbox / "001.json").exists()
    assert (data_dir / "processed" / "crowd").exists()
    assert (data_dir / "series" / "crowd_reports.jsonl").exists()

# ---------------------------------------------------------------------------
# Review follow-ups: the PII scanner's failure direction, and inbox deletion.
# ---------------------------------------------------------------------------


def test_pii_scanning_covers_fields_nobody_thought_to_allowlist() -> None:
    """A field added to the schema later must be scanned by default.

    The first version applied the phone and email patterns only to six named
    free-text keys. Any field added afterwards silently went unscanned, which is
    the wrong failure direction for a privacy guard.
    """
    for field in ("landmark", "description", "reference", "comment_en", "what_i_saw"):
        with pytest.raises(PrivacyError):
            assert_no_pii({field: "ring me on 9876543210"})
        with pytest.raises(PrivacyError):
            assert_no_pii({field: "mail me at flood@example.com"})


def test_machine_identifiers_stay_exempt_from_phone_matching() -> None:
    """SHA-256 digests routinely contain ten consecutive digits."""
    digest = "a" * 22 + "6789012345" + "b" * 32
    assert_no_pii({"device_hash": digest})
    assert_no_pii({"report_id": digest})
    # But the same value under a reporter-facing key is still caught.
    with pytest.raises(PrivacyError):
        assert_no_pii({"landmark": digest})


def test_booleans_are_not_mistaken_for_banned_coordinates() -> None:
    """True == 1 in Python, so a banned value of 1 must not match a flag."""
    assert_no_pii({"revised": True, "queued": False}, banned_values={1, 0})


def test_an_empty_submission_file_is_not_deleted(tmp_path: Path) -> None:
    """Deleting a file we read nothing out of would destroy a real submission."""
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    empty = inbox / "empty.json"
    empty.write_text("[]")

    result = ingest_crowd_inbox(inbox=inbox, data_dir=tmp_path / "data")

    assert empty.exists(), "a file that yielded no records must survive"
    assert result["raw_files_deleted"] == 0
    assert str(empty) in result["skipped_empty_files"]


def test_a_bad_item_aborts_before_anything_in_its_batch_is_stored(tmp_path: Path) -> None:
    """Otherwise the good half is ingested, the file stays, and a retry doubles it."""
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    data_dir = tmp_path / "data"
    batch = inbox / "batch.json"
    batch.write_text(
        json.dumps(
            [
                {
                    "location": [94.6812345, 26.9123456],
                    "depth_class": "knee",
                    "locality_id": "nagaon-kampur",
                    "source": "app",
                    "device_token": "device-a",
                },
                {"record_type": "nonsense"},
            ]
        )
    )

    with pytest.raises(ValueError, match="unknown record_type"):
        ingest_crowd_inbox(inbox=inbox, data_dir=data_dir)

    assert batch.exists(), "the raw file must survive a rejected batch"
    series = list((data_dir / "series").rglob("*.jsonl")) if (data_dir / "series").exists() else []
    stored = sum(
        1 for path in series for line in path.read_text().splitlines() if line.strip()
    )
    assert stored == 0, "no item from a rejected batch may reach the series"


# --- identifiers must not look like phone numbers ------------------------


#: A real uuid4, chosen because "9588952247" inside it is exactly an Indian
#: mobile number to `_PHONE`. Hard-coded rather than generated so this test
#: cannot itself become the flaky thing it is guarding against.
PHONE_SHAPED_UUID = "8a764358-3236-48ec-9ae3-9588952247ab"


def test_a_machine_generated_id_is_never_mistaken_for_a_phone_number():
    """The bug this catches failed about one submission in three hundred.

    `hwm_id` is a uuid4 and was not exempt from phone-pattern scanning, so any
    high-water mark whose id happened to contain ten consecutive digits starting
    6-9 was rejected as carrying PII. It surfaced as a test that passed on its
    own and failed in a full run, which is the worst way to find a bug that was
    also rejecting real submissions.
    """

    record, banned = build_high_water_mark(
        {
            "latitude": 26.9123456789,
            "longitude": 94.6801234567,
            "year": 2023,
            "depth_cm": 110,
            "reference_en": "up to the window sill",
            "confidence": "recalled",
            "hwm_id": PHONE_SHAPED_UUID,
        },
        now=NOW,
    )

    assert record["hwm_id"] == PHONE_SHAPED_UUID
    assert_no_pii(record, banned_values=banned)


def test_every_identifier_the_crowd_pipeline_emits_is_exempt_from_scanning():
    """A guard on the guard.

    Exempting by field name is the right default — a `landmark` field added
    later must be scanned, not silently trusted. The cost is that a forgotten
    identifier fails randomly. This asserts the exemption list actually covers
    the identifiers the pipeline emits, so the next one is caught at the bench.
    """

    report, _ = build_crowd_report(
        {
            "latitude": 26.9123456789,
            "longitude": 94.6801234567,
            "depth_class": "knee",
            "locality_id": "baksa-barama-pt",
            "device_token": "d" * 40,
            "source": "app",
            "submitted_at": NOW.isoformat(),
        },
        salt=b"0123456789abcdef0123456789abcdef",
        month="2026-07",
        now=NOW,
    )
    mark, _ = build_high_water_mark(
        {
            "latitude": 26.9123456789,
            "longitude": 94.6801234567,
            "year": 2023,
            "depth_cm": 110,
            "reference_en": "up to the window sill",
        },
        now=NOW,
    )

    emitted = {
        key
        for record in (report, mark)
        for key in record
        if key.endswith(("_id", "_hash", "_sha256", "_revision"))
    }
    unscanned = {re.sub(r"[-_]", "", key) for key in emitted}
    assert unscanned <= _UNSCANNED_KEYS, sorted(unscanned - _UNSCANNED_KEYS)
