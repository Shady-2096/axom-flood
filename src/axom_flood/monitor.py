"""Evidence ledger for the Phase 0 unattended-run acceptance criterion."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .artifacts import newest_by_field, pointed_at, the_only_one

IST = ZoneInfo("Asia/Kolkata")

# What this ledger is evidence *of*, and how each source names its current
# artifact.
#
# The rule used to be newest modification time for all seven, which is the bug
# `artifacts.py` exists to remove. It was already producing wrong evidence: the
# two directories that carry a `current.json` were resolving to the pointer
# itself, because a pointer is written after the artifact it names and so is
# always the newest file. The ledger recorded the sha256 of a forty-line pointer
# as proof that a camp match ran.
#
# `pointer` where a writer leaves one, the artifact's own timestamp where it does
# not, and a refusal for the UDISE roster, which is a hand-pinned 2021 mirror
# where "the newest" is not a question with an answer.
REQUIRED_ARTIFACTS: dict[str, tuple[str, str, str]] = {
    "asdma": ("processed/asdma", "*/*.json", "report_date"),
    "camps": ("processed/district-camps", "*.json", "generated_at"),
    "udise": ("reference/udise", "assam-schools-*.csv", "only"),
    "camp_matches": ("processed/camp-matches", "*.json", "pointer"),
    "gauges": ("processed/gauges", "*.json", "generated_at"),
    "cwc": ("processed/cwc", "*.json", "pointer"),
    "smart_axom": ("processed/smart-axom", "*.json", "fetched_at"),
}

RUN_ORIGINS = {"schedule", "workflow_dispatch", "local"}


def _latest(root: Path, pattern: str, rule: str) -> Path:
    try:
        if rule == "pointer":
            return pointed_at(root)
        if rule == "only":
            return the_only_one(root, pattern)
        return newest_by_field(root, pattern, rule)
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"missing Phase 0 artifact: {root / pattern}") from exc


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
    for pipeline, (directory, pattern, rule) in REQUIRED_ARTIFACTS.items():
        path = _latest(data_dir / directory, pattern, rule)
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
