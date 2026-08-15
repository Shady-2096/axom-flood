"""Run the Phase 1 alert engine over the newest immutable CWC snapshot."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from ..artifacts import pointed_at
from .engine import evaluate_alert, persist_alert_artifacts

IST = ZoneInfo("Asia/Kolkata")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def _append_once(path: Path, record: dict[str, Any]) -> None:
    existing = {item["alert_id"] for item in _read_jsonl(path)}
    if record["alert_id"] in existing:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def _last_by_locality(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for record in records:
        result[record["locality_id"]] = record
    return result


def run_alerts(
    *,
    data_dir: Path,
    localities_path: Path = Path("config/assam-localities.json"),
    cwc_snapshot: Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or datetime.now(IST)
    # By the pointer the CWC ingest writes, never by modification time. This
    # picked `max(..., key=st_mtime)` until it was found to be wrong twice over:
    # a fresh `git clone` stamps all 213 snapshots at once so the pick was
    # arbitrary, and `current.json` is itself in that directory and written last,
    # so the newest file was usually the pointer -- which has no `stations` and
    # failed the whole run with a KeyError.
    cwc_path = cwc_snapshot or pointed_at(data_dir / "processed" / "cwc")
    cwc = json.loads(cwc_path.read_text())
    localities = json.loads(localities_path.read_text())["localities"]
    stations = {item["cwc_station_code"]: item for item in cwc["stations"]}
    ledger_path = data_dir / "series" / "alerts.jsonl"
    history = _read_jsonl(ledger_path)
    previous = _last_by_locality(history)
    emitted: list[dict[str, Any]] = []

    for locality in localities:
        gauge = stations.get(locality["primary_gauge"])
        if gauge is None:
            continue
        prior = previous.get(locality["locality_id"])
        active_event = bool(
            (prior and prior["severity"] in {"watch", "high", "severe"})
            or (
                gauge.get("level_m") is not None
                and gauge.get("danger_level_m") is not None
                and float(gauge["level_m"]) >= float(gauge["danger_level_m"])
            )
        )
        series_path = data_dir / "series" / "gauges" / f"{gauge['gauge_id']}.jsonl"
        readings = _read_jsonl(series_path)
        previous_push = None
        for record in reversed(history):
            if record["locality_id"] == locality["locality_id"] and record.get("push"):
                previous_push = record
                break
        alert = evaluate_alert(
            locality,
            gauge,
            readings,
            now=now,
            active_event=active_event,
            previous_push=previous_push,
        )
        if alert is None:
            continue
        artifact_dir = data_dir / "processed" / "alerts"
        paths = persist_alert_artifacts(alert, output_dir=artifact_dir)
        alert_path = artifact_dir / alert["alert_id"] / "alert.json"
        payload = json.dumps(alert, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        if alert_path.exists() and alert_path.read_text() != payload:
            raise RuntimeError(f"refusing to overwrite immutable alert: {alert_path}")
        if not alert_path.exists():
            alert_path.write_text(payload)
        _append_once(ledger_path, alert)
        emitted.append({**alert, "artifacts": {**paths, "alert": str(alert_path)}})

    return {
        "schema_version": 1,
        "generated_at": now.isoformat(),
        "cwc_snapshot": str(cwc_path),
        "localities_evaluated": sum(
            1 for locality in localities if locality["primary_gauge"] in stations
        ),
        "alerts_emitted": len(emitted),
        "pushes_ready": sum(1 for alert in emitted if alert["push"]),
        "alerts": emitted,
    }
