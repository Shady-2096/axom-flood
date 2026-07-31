"""Evidence ledger for the Phase 0 unattended-run acceptance criterion."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

REQUIRED_ARTIFACTS = {
    "asdma": ("processed/asdma", "*/*.json"),
    "camps": ("processed/district-camps", "*.json"),
    "udise": ("reference/udise", "assam-schools-*.csv"),
    "camp_matches": ("processed/camp-matches", "*.json"),
    "gauges": ("processed/gauges", "*.json"),
    "cwc": ("processed/cwc", "*.json"),
    "smart_axom": ("processed/smart-axom", "*.json"),
}

RUN_ORIGINS = {"schedule", "workflow_dispatch", "local"}


def _latest(root: Path, pattern: str) -> Path:
    matches = list(root.glob(pattern))
    if not matches:
        raise FileNotFoundError(f"missing Phase 0 artifact: {root / pattern}")
    return max(matches, key=lambda path: path.stat().st_mtime)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def record_success(
    *,
    data_dir: Path,
    now: datetime | None = None,
    run_id: str | None = None,
    run_origin: str = "local",
) -> dict[str, Any]:
    """Append one successful orchestration record after every pipeline exits cleanly."""

    if run_origin not in RUN_ORIGINS:
        raise ValueError(
            f"unsupported run origin {run_origin!r}; expected one of {sorted(RUN_ORIGINS)}"
        )
    now = now or datetime.now(IST)
    artifacts: dict[str, Any] = {}
    for pipeline, (directory, pattern) in REQUIRED_ARTIFACTS.items():
        path = _latest(data_dir / directory, pattern)
        artifact: dict[str, Any] = {
            "path": str(path.relative_to(data_dir.parent)),
            "sha256": _sha256(path),
        }
        if path.suffix == ".json":
            document = json.loads(path.read_text())
            if "status" in document:
                artifact["source_status"] = document["status"]
            if "issued_at" in document:
                artifact["source_issued_at"] = document["issued_at"]
        artifacts[pipeline] = artifact

    record = {
        "schema_version": 2,
        "run_date": now.date().isoformat(),
        "recorded_at": now.isoformat(),
        "status": "success",
        "run_id": run_id,
        "run_origin": run_origin,
        "artifacts": artifacts,
    }
    ledger = data_dir / "monitor" / "phase0-runs.jsonl"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.open("a") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    return record


def monitor_status(*, data_dir: Path, today: date | None = None) -> dict[str, Any]:
    """Return distinct successful days and the current consecutive-day streak."""

    today = today or datetime.now(IST).date()
    ledger = data_dir / "monitor" / "phase0-runs.jsonl"
    records = [
        json.loads(line)
        for line in ledger.read_text().splitlines()
        if line.strip()
    ] if ledger.exists() else []
    scheduled_successful_dates = sorted(
        {
            date.fromisoformat(record["run_date"])
            for record in records
            if record.get("status") == "success"
            and record.get("run_origin") == "schedule"
        }
    )
    verification_successful_dates = sorted(
        {
            date.fromisoformat(record["run_date"])
            for record in records
            if record.get("status") == "success"
            and record.get("run_origin") != "schedule"
        }
    )
    streak = 0
    cursor = today
    successful_set = set(scheduled_successful_dates)
    while cursor in successful_set:
        streak += 1
        cursor -= timedelta(days=1)
    return {
        "schema_version": 2,
        "acceptance_target_days": 30,
        "successful_distinct_days": len(scheduled_successful_dates),
        "current_consecutive_days": streak,
        "target_met": streak >= 30,
        "latest_successful_date": (
            scheduled_successful_dates[-1].isoformat()
            if scheduled_successful_dates
            else None
        ),
        "verification_distinct_days": len(verification_successful_dates),
        "latest_verification_date": (
            verification_successful_dates[-1].isoformat()
            if verification_successful_dates
            else None
        ),
    }
