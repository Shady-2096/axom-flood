import json
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from axom_flood.monitor import REQUIRED_ARTIFACTS, monitor_status, record_success


def test_monitor_records_artifacts_and_counts_distinct_consecutive_days(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    for directory, pattern in REQUIRED_ARTIFACTS.values():
        suffix = ".csv" if pattern.endswith(".csv") else ".json"
        filename = "assam-schools-test.csv" if suffix == ".csv" else f"artifact{suffix}"
        path = data_dir / directory / filename
        if "*" in directory:
            raise AssertionError("test fixture does not support wildcard directories")
        if pattern.startswith("*/*"):
            path = data_dir / directory / "2026-07-26" / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("name\nschool\n" if suffix == ".csv" else "{}\n")

    ist = ZoneInfo("Asia/Kolkata")
    record_success(
        data_dir=data_dir,
        now=datetime(2026, 7, 25, 20, tzinfo=ist),
        run_id="test-1",
        run_origin="schedule",
    )
    record_success(
        data_dir=data_dir,
        now=datetime(2026, 7, 26, 20, tzinfo=ist),
        run_id="test-2",
        run_origin="schedule",
    )
    # A retry on the same day remains evidence but does not inflate the streak.
    record_success(
        data_dir=data_dir,
        now=datetime(2026, 7, 26, 21, tzinfo=ist),
        run_id="test-3",
        run_origin="schedule",
    )

    status = monitor_status(data_dir=data_dir, today=date(2026, 7, 26))
    assert status["successful_distinct_days"] == 2
    assert status["current_consecutive_days"] == 2
    assert status["target_met"] is False
    records = [
        json.loads(line)
        for line in (data_dir / "monitor" / "phase0-runs.jsonl").read_text().splitlines()
    ]
    assert records[-1]["artifacts"]["asdma"]["sha256"]
    assert records[-1]["run_origin"] == "schedule"


def test_monitor_excludes_manual_local_and_legacy_records_from_acceptance(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "data"
    ledger = data_dir / "monitor" / "phase0-runs.jsonl"
    ledger.parent.mkdir(parents=True)
    records = [
        {"run_date": "2026-07-24", "status": "success"},
        {
            "run_date": "2026-07-25",
            "status": "success",
            "run_origin": "local",
        },
        {
            "run_date": "2026-07-26",
            "status": "success",
            "run_origin": "workflow_dispatch",
        },
        {
            "run_date": "2026-07-26",
            "status": "success",
            "run_origin": "schedule",
        },
    ]
    ledger.write_text("\n".join(json.dumps(record) for record in records) + "\n")

    status = monitor_status(data_dir=data_dir, today=date(2026, 7, 26))

    assert status["successful_distinct_days"] == 1
    assert status["current_consecutive_days"] == 1
    assert status["verification_distinct_days"] == 3
    assert status["latest_verification_date"] == "2026-07-26"


def test_record_success_rejects_unknown_origin(tmp_path: Path) -> None:
    try:
        record_success(data_dir=tmp_path / "data", run_origin="manual")
    except ValueError as exc:
        assert "unsupported run origin" in str(exc)
    else:
        raise AssertionError("record_success accepted an unknown run origin")
