import json
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from axom_flood.monitor import REQUIRED_ARTIFACTS, monitor_status, record_success


def _write_artifacts(data_dir: Path, *, field_value: str = "2026-07-26T20:00:00+05:30") -> None:
    """One artifact per required source, shaped the way its own rule reads it.

    The fixture used to write `{}` for every one of them, which passed only
    because the selection rule was newest-modification-time and never opened the
    file. Each source now names how it is chosen -- a pointer, its own timestamp
    field, or being the only file -- so the fixture has to satisfy that rule, and
    a source whose artifacts stop carrying its field now fails here.
    """

    for directory, pattern, rule in REQUIRED_ARTIFACTS.values():
        if "*" in directory:
            raise AssertionError("test fixture does not support wildcard directories")
        root = data_dir / directory
        if rule == "only":
            path = root / "assam-schools-test.csv"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("name\nschool\n")
            continue
        parent = root / "2026-07-26" if pattern.startswith("*/*") else root
        parent.mkdir(parents=True, exist_ok=True)
        body: dict[str, str] = {} if rule == "pointer" else {rule: field_value}
        (parent / "artifact.json").write_text(json.dumps(body) + "\n")
        if rule == "pointer":
            root.mkdir(parents=True, exist_ok=True)
            (root / "current.json").write_text(json.dumps({"revision_id": "artifact"}) + "\n")


def test_monitor_records_the_artifact_a_pointer_names_not_the_pointer(
    tmp_path: Path,
) -> None:
    """The ledger is evidence that a pipeline ran, so it has to hash its output.

    Both pointer-backed sources resolved to `current.json` under the old
    modification-time rule -- a pointer is written after the artifact it names,
    so it is always the newest file in the directory. The ledger recorded the
    sha256 of a forty-line pointer as proof that a camp match had run.
    """

    data_dir = tmp_path / "data"
    _write_artifacts(data_dir)
    record_success(data_dir=data_dir, run_id="test-pointer", run_origin="schedule")

    records = [
        json.loads(line)
        for line in (data_dir / "monitor" / "phase0-runs.jsonl").read_text().splitlines()
    ]
    for pipeline, (_, _, rule) in REQUIRED_ARTIFACTS.items():
        recorded = records[-1]["artifacts"][pipeline]["path"]
        assert not recorded.endswith("current.json"), f"{pipeline} recorded the pointer"
        if rule == "pointer":
            assert recorded.endswith("artifact.json")


def test_monitor_records_artifacts_and_counts_distinct_consecutive_days(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    _write_artifacts(data_dir)

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
