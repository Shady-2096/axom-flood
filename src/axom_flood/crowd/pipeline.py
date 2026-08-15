"""Ingest and publish crowd reports.

Ingest is the single point in the project where a raw submission &mdash; which
by spec carries full-precision GPS and a raw device token &mdash; is turned
into the anonymised, published shape the plan defines. The raw submission is
never persisted: the inbox file is deleted once the rounded, hashed record is
appended to the append-only series.

The published artefacts follow the project's content-hashed immutable
convention:

* ``data/series/crowd_reports.jsonl`` &mdash; append-only, one anonymised
  report per line, deduplicated by ``report_id``.
* ``data/processed/crowd/<sha256>.json`` &mdash; the reconciled open dataset
  (display rules applied) written once and never overwritten.
* ``data/series/high_water_marks.jsonl`` and
  ``data/processed/high-water-marks/<sha256>.json`` &mdash; the separate,
  never-mixed recalled-history store that seeds Phase 4.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from ..artifacts import pointed_at
from .aggregate import load_locality_index, reconcile_dataset
from .privacy import (
    MIN_PRECISION_M,
    PrivacyError,
    assert_no_pii,
    device_hash,
    month_string,
    round_coordinate,
)

IST = ZoneInfo("Asia/Kolkata")

DEPTH_CLASSES = ("dry", "ankle", "knee", "waist_plus")
SOURCES = ("app", "whatsapp", "web")
HWM_CONFIDENCE = ("recalled", "corroborated")

CROWD_SERIES = Path("data/series/crowd_reports.jsonl")
CROWD_PROCESSED_DIR = Path("data/processed/crowd")
HWM_SERIES = Path("data/series/high_water_marks.jsonl")
HWM_PROCESSED_DIR = Path("data/processed/high-water-marks")
SALT_CACHE_DIR = Path("data/cache/crowd")


# ---------------------------------------------------------------------------
# Salt management
# ---------------------------------------------------------------------------


def load_month_salt(month: str, *, cache_dir: Path | None = None) -> bytes:
    """Return the operator-controlled salt for a month, rotating monthly.

    The salt lives under gitignored ``data/cache/crowd/`` keyed by month so it
    is stable within a month (required for duplicate detection) and rotates
    automatically at the month boundary. Tests pass their own salt; production
    reads this cache, creating the first salt for a month lazily.
    """
    directory = (cache_dir or SALT_CACHE_DIR)
    path = directory / f"salt-{month}.bin"
    if path.exists():
        return path.read_bytes()
    directory.mkdir(parents=True, exist_ok=True)
    salt = secrets.token_bytes(32)
    # 0600 so the salt file is at least not world-readable on shared runners.
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, salt)
    finally:
        os.close(fd)
    return salt


# ---------------------------------------------------------------------------
# Submission validation
# ---------------------------------------------------------------------------


def _require(submission: dict[str, Any], key: str) -> Any:
    if key not in submission:
        raise ValueError(f"submission missing required field: {key!r}")
    return submission[key]


#: Closed allow-list of submission keys. Anything else is rejected so a stray
#: ``name``/``phone``/``imei`` field cannot be silently ingested.
CROWD_SUBMISSION_KEYS = {
    "latitude",
    "longitude",
    "depth_class",
    "device_token",
    "source",
    "submitted_at",
    "locality_id",
    "report_id",
}
HWM_SUBMISSION_KEYS = {
    "latitude",
    "longitude",
    "year",
    "depth_cm",
    "reference_en",
    "confidence",
    "submitted_at",
    "hwm_id",
}


def _seal_keys(submission: dict[str, Any], allowed: set[str]) -> None:
    extra = set(submission) - allowed
    if extra:
        raise PrivacyError(
            f"submission carries unexpected field(s): {sorted(extra)}; "
            f"allowed: {sorted(allowed)}"
        )


def _banned_from_submission(submission: dict[str, Any], *, lat: float, lon: float) -> set[Any]:
    """Values that must never survive into a stored record.

    The raw full-precision coordinate and the raw device token are both banned
    audit-value witnesses: if either appears anywhere in a published record,
    the privacy test fails loudly.

    A submitter that has *already* coarsened its coordinate is the case this
    has to be careful about. The browser rounds on the device before queueing,
    and the reporting database stores three decimals under a column check, so
    both send a value identical to the one the stored record legitimately
    carries. Banning it unconditionally would make the most privacy-preserving
    inputs the only ones that fail the privacy check. So a coordinate is only
    treated as a witness when rounding actually changed it — which is exactly
    when full precision was present and must not survive.
    """
    banned: set[Any] = set()
    for raw, rounded in ((submission["latitude"], lat), (submission["longitude"], lon)):
        if float(raw) == float(rounded):
            continue
        banned.update({raw, float(raw), str(raw)})
    token = submission.get("device_token")
    if token is not None:
        banned.add(token)
    return banned


def build_crowd_report(
    submission: dict[str, Any],
    *,
    salt: bytes,
    month: str,
    now: datetime | None = None,
) -> tuple[dict[str, Any], set[Any]]:
    """Build the published ``crowd_report`` shape from a raw submission.

    Returns the anonymised record and the set of banned audit values the
    caller should pass to ``assert_no_pii`` on whatever it persists.

    Raises ``ValueError`` or ``PrivacyError`` on any malformed or PII-carrying
    submission.
    """
    now = now or datetime.now(IST)
    _seal_keys(submission, CROWD_SUBMISSION_KEYS)
    _require(submission, "latitude")
    _require(submission, "longitude")
    _require(submission, "depth_class")
    _require(submission, "device_token")

    raw_lat = float(submission["latitude"])
    raw_lon = float(submission["longitude"])
    lat, lon = round_coordinate(raw_lat, raw_lon)

    depth = submission["depth_class"]
    if depth not in DEPTH_CLASSES:
        raise ValueError(f"unknown depth_class {depth!r}; expected one of {DEPTH_CLASSES}")

    source = submission.get("source", "app")
    if source not in SOURCES:
        raise ValueError(f"unknown source {source!r}; expected one of {SOURCES}")

    token = submission["device_token"]
    dh = device_hash(token, salt, month)

    submitted_at_raw = submission.get("submitted_at")
    submitted_at = (
        datetime.fromisoformat(submitted_at_raw)
        if isinstance(submitted_at_raw, str)
        else submitted_at_raw or now
    )
    if submitted_at.tzinfo is None:
        submitted_at = submitted_at.replace(tzinfo=IST)
    if submitted_at > now:
        raise ValueError("submitted_at is in the future")

    locality_id = submission.get("locality_id")
    if locality_id is not None and not isinstance(locality_id, str):
        raise ValueError("locality_id must be a string or null")

    report = {
        "schema_version": 1,
        "report_id": submission.get("report_id") or str(uuid.uuid4()),
        "submitted_at": submitted_at.isoformat(),
        "location": [lon, lat],
        "location_precision_m": MIN_PRECISION_M,
        "depth_class": depth,
        "locality_id": locality_id,
        "source": source,
        "device_hash": dh,
        "flags": [],
    }
    banned = _banned_from_submission(submission, lat=raw_lat, lon=raw_lon)
    assert_no_pii(report, banned_values=banned)
    return report, banned


def build_high_water_mark(
    submission: dict[str, Any],
    *,
    now: datetime | None = None,
) -> tuple[dict[str, Any], set[Any]]:
    """Build the published high-water-mark record from a raw submission.

    The stored shape matches ``assam-flood-implementation-plan.md`` PART 4
    §2.5 exactly: ``location``, ``year``, ``depth_cm``, ``reference_en``,
    ``confidence``. ``schema_version`` is added per the repo-wide rule that
    every artifact carries one (``schemas/README.md``); a separate ``hwm_id``
    and ``submitted_at`` provenance pair ride along on the container so the
    recalled record itself stays in the plan's exact shape.
    """
    now = now or datetime.now(IST)
    _seal_keys(submission, HWM_SUBMISSION_KEYS)
    _require(submission, "latitude")
    _require(submission, "longitude")
    _require(submission, "year")
    _require(submission, "depth_cm")
    _require(submission, "reference_en")

    raw_lat = float(submission["latitude"])
    raw_lon = float(submission["longitude"])
    lat, lon = round_coordinate(raw_lat, raw_lon)

    year = int(submission["year"])
    depth_cm = int(submission["depth_cm"])
    reference_en = str(submission["reference_en"])[:200]
    confidence = submission.get("confidence", "recalled")
    if confidence not in HWM_CONFIDENCE:
        raise ValueError(f"confidence must be one of {HWM_CONFIDENCE}")

    record = {
        "schema_version": 1,
        "hwm_id": submission.get("hwm_id") or str(uuid.uuid4()),
        "submitted_at": (
            datetime.fromisoformat(submission["submitted_at"])
            if isinstance(submission.get("submitted_at"), str)
            else now
        ).isoformat(),
        "location": [lon, lat],
        "year": year,
        "depth_cm": depth_cm,
        "reference_en": reference_en,
        "confidence": confidence,
    }
    banned: set[Any] = {
        raw_lat,
        raw_lon,
        float(raw_lat),
        float(raw_lon),
        str(raw_lat),
        str(raw_lon),
    }
    assert_no_pii(record, banned_values=banned)
    return record, banned


# ---------------------------------------------------------------------------
# Series append
# ---------------------------------------------------------------------------


def _existing_ids(path: Path, id_key: str) -> set[str]:
    if not path.exists():
        return set()
    found: set[str] = set()
    for line in path.read_text().splitlines():
        if not line:
            continue
        found.add(json.loads(line)[id_key])
    return found


def _append(path: Path, record: dict[str, Any], *, id_key: str) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = _existing_ids(path, id_key)
    if record[id_key] in existing:
        return False
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    return True


def _write_immutable(directory: Path, document: dict[str, Any], *, name_prefix: str = "") -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
    artifact_id = hashlib.sha256(payload).hexdigest()
    path = directory / f"{name_prefix}{artifact_id}.json"
    if path.exists() and path.read_bytes() != payload:
        raise RuntimeError(f"refusing to overwrite immutable artifact: {path}")
    if not path.exists():
        path.write_bytes(payload)
    return path


# ---------------------------------------------------------------------------
# Public ingest + publish
# ---------------------------------------------------------------------------


def ingest_crowd_submission(
    submission: dict[str, Any],
    *,
    data_dir: Path,
    salt: bytes,
    month: str | None = None,
    now: datetime | None = None,
    series_path: Path | None = None,
) -> dict[str, Any]:
    """Validate, anonymise and append one crowd report to the series."""
    now = now or datetime.now(IST)
    month = month or month_string(now)
    report, banned = build_crowd_report(submission, salt=salt, month=month, now=now)
    series = series_path or (data_dir / "series" / "crowd_reports.jsonl")
    appended = _append(series, report, id_key="report_id")
    return {"report": report, "appended": appended, "banned_values_count": len(banned)}


def ingest_high_water_mark(
    submission: dict[str, Any],
    *,
    data_dir: Path,
    now: datetime | None = None,
    series_path: Path | None = None,
) -> dict[str, Any]:
    """Validate and append one recalled high-water mark to its separate series."""
    now = now or datetime.now(IST)
    record, banned = build_high_water_mark(submission, now=now)
    series = series_path or (data_dir / "series" / "high_water_marks.jsonl")
    appended = _append(series, record, id_key="hwm_id")
    return {"record": record, "appended": appended, "banned_values_count": len(banned)}


def publish_open_dataset(
    *,
    data_dir: Path,
    localities_path: Path,
    now: datetime | None = None,
    active_event: bool | None = None,
    series_path: Path | None = None,
) -> dict[str, Any]:
    """Publish the reconciled, content-hashed aggregate-only crowd dataset.

    When the caller does not explicitly set event mode, a fresh CWC snapshot
    decides it. This keeps the 12-hour hide rule from silently remaining off
    during a live threshold event.
    """
    now = now or datetime.now(IST)
    event_detection = "explicit"
    if active_event is None:
        active_event = _detect_active_event(data_dir=data_dir, now=now)
        event_detection = "fresh_cwc_snapshot"
    series = series_path or (data_dir / "series" / "crowd_reports.jsonl")
    reports = []
    if series.exists():
        for line in series.read_text().splitlines():
            if line:
                reports.append(json.loads(line))
    localities = load_locality_index(localities_path)
    document = reconcile_dataset(
        reports,
        now=now,
        localities=localities,
        active_event=active_event,
    )
    document["event_detection"] = event_detection
    path = _write_immutable(data_dir / "processed" / "crowd", document)
    return {
        "artifact_id": Path(path).stem,
        "report_count_total": document["report_count_total"],
        "report_count_visible": document["report_count_visible"],
        "aggregate_statements": len(document["aggregate_statements"]),
        "json": str(path),
    }


def _detect_active_event(
    *,
    data_dir: Path,
    now: datetime,
    fresh_for_hours: float = 6.0,
) -> bool:
    """Return true only for a fresh CWC snapshot with a danger exceedance.

    By the pointer the ingest writes. This used to parse all 213 committed
    snapshots to find the newest `generated_at` -- the right key, so the answer
    was correct, but at the cost of reading every river snapshot the project has
    ever published on a code path that only needs one of them.

    A missing pointer is not fatal here. Event mode decides whether recent crowd
    reports are held back for twelve hours, and the safe reading of "we cannot
    tell" is the same as it has always been: no event, so nothing is hidden.
    """
    try:
        latest = json.loads(pointed_at(data_dir / "processed" / "cwc").read_text())
        generated = datetime.fromisoformat(latest["generated_at"])
    except (OSError, RuntimeError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return False
    if generated.tzinfo is None:
        generated = generated.replace(tzinfo=IST)
    age_hours = max(0.0, (now - generated).total_seconds() / 3600.0)
    return (
        age_hours <= fresh_for_hours
        and int(latest.get("stations_at_or_above_danger") or 0) > 0
    )


def publish_high_water_mark_set(
    *,
    data_dir: Path,
    now: datetime | None = None,
    series_path: Path | None = None,
) -> dict[str, Any]:
    """Publish the recalled high-water-mark snapshot, separate from live reports."""
    now = now or datetime.now(IST)
    series = series_path or (data_dir / "series" / "high_water_marks.jsonl")
    records: list[dict[str, Any]] = []
    if series.exists():
        for line in series.read_text().splitlines():
            if line:
                records.append(json.loads(line))
    document = {
        "schema_version": 1,
        "generated_at": now.isoformat(),
        "record_count": len(records),
        "records": records,
        "source_series": str(series),
    }
    path = _write_immutable(
        data_dir / "processed" / "high-water-marks", document, name_prefix=""
    )
    return {
        "artifact_id": Path(path).stem,
        "record_count": len(records),
        "json": str(path),
    }


# ---------------------------------------------------------------------------
# Inbox ingest + raw-source erasure
# ---------------------------------------------------------------------------


def ingest_crowd_inbox(
    *,
    inbox: Path,
    data_dir: Path,
    now: datetime | None = None,
    delete_raw: bool = True,
) -> dict[str, Any]:
    """Ingest every submission file in an inbox directory.

    A submission file is one JSON object (``crowd``) or a JSON array of
    submissions (``hwm`` via ``record_type``). After the anonymised record is
    appended to the series, the raw submission file is deleted so the
    full-precision coordinate and raw device token are never persisted.

    Returns a per-file summary. ``raw_files_deleted`` is the number of raw
    submission files removed; the test suite asserts it equals the number
    ingested when ``delete_raw`` is true.
    """
    now = now or datetime.now(IST)
    month = month_string(now)
    salt = load_month_salt(month, cache_dir=data_dir / "cache" / "crowd")

    files = sorted(p for p in inbox.iterdir() if p.is_file() and p.suffix == ".json")
    ingested = 0
    duplicates = 0
    raw_deleted = 0
    hwm_ingested = 0
    skipped_empty: list[str] = []
    for path in files:
        try:
            payload = json.loads(path.read_text())
        except json.JSONDecodeError as exc:
            raise ValueError(f"unreadable submission {path}: {exc}") from exc
        if isinstance(payload, list):
            items = payload
        elif isinstance(payload, dict) and "submissions" in payload:
            items = payload["submissions"]
        else:
            items = [payload]

        # Every item is validated before anything is appended, so a bad item
        # part-way through a batch cannot leave the first half ingested and the
        # file still on disk — which on the next run would re-ingest them.
        for item in items:
            kind = item.get("record_type", "crowd")
            if kind not in ("crowd", "hwm"):
                raise ValueError(f"unknown record_type {kind!r} in {path}")

        if not items:
            # Deleting a file that contributed nothing would destroy a
            # submission we never actually read. Leave it and say so.
            skipped_empty.append(str(path))
            continue

        for item in items:
            kind = item.get("record_type", "crowd")
            cleaned = {k: v for k, v in item.items() if k != "record_type"}
            if kind == "hwm":
                result = ingest_high_water_mark(cleaned, data_dir=data_dir, now=now)
                hwm_ingested += 1
                if not result["appended"]:
                    duplicates += 1
                continue
            result = ingest_crowd_submission(
                cleaned, data_dir=data_dir, salt=salt, month=month, now=now
            )
            ingested += 1
            if not result["appended"]:
                duplicates += 1
        if delete_raw:
            # Only now, with every item in this file durably appended: the raw
            # file holds the full-precision coordinate and the raw device token,
            # so it must not outlive ingestion.
            path.unlink()
            raw_deleted += 1
    return {
        "schema_version": 1,
        "ingested": ingested,
        "hwm_ingested": hwm_ingested,
        "duplicates": duplicates,
        "raw_files_deleted": raw_deleted,
        # Files left in place because they held no submissions. Surfaced rather
        # than deleted, so an operator can see something arrived malformed.
        "skipped_empty_files": skipped_empty,
        "month": month,
    }


__all__ = [
    "build_crowd_report",
    "build_high_water_mark",
    "ingest_crowd_inbox",
    "ingest_crowd_submission",
    "ingest_high_water_mark",
    "load_month_salt",
    "publish_high_water_mark_set",
    "publish_open_dataset",
]
