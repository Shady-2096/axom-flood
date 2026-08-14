"""Command-line entry point for unattended Phase 0 jobs."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .alerts.pipeline import run_alerts
from .asdma import BulletinNotFound, fetch_bulletin, persist_bulletin
from .asdma.parser import BulletinParseError
from .asdma.publisher import (
    DEFAULT_FRESHNESS_DAYS,
    publish_impact,
    quarantine_source_failure,
)
from .camps import run_camp_pipeline
from .crowd import (
    ingest_crowd_inbox,
    load_month_salt,
    month_string,
    publish_high_water_mark_set,
    publish_open_dataset,
)
from .crowd.exporter import SupabaseReportSource, export_reports
from .cwc import ingest_cwc_gauges
from .flews import ingest_public_flood_alerts
from .gauges import ingest_gauge_csv
from .monitor import monitor_status, record_success
from .udise import DEFAULT_SOURCE_URL, ingest_assam_schools, match_camps_to_schools

IST = ZoneInfo("Asia/Kolkata")


def _write_run_status(data_dir: Path, status: dict[str, Any]) -> Path:
    now = datetime.now(IST)
    path = data_dir / "run-status" / "asdma" / f"{now.strftime('%Y%m%dT%H%M%S%z')}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(status, indent=2, sort_keys=True) + "\n")
    return path


def _run_camps(args: argparse.Namespace) -> int:
    try:
        result = run_camp_pipeline(
            registry_path=Path(args.registry),
            data_dir=Path(args.data_dir),
            timeout_seconds=args.timeout,
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        print(f"camp pipeline failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


def _candidates(path: Path, pattern: str) -> list[Path]:
    matches = sorted(path.glob(pattern))
    if not matches:
        raise FileNotFoundError(f"no files matching {path / pattern}")
    return matches


def _newest_by_field(path: Path, pattern: str, field: str) -> Path:
    """The artifact whose own `field` is latest.

    These used to be chosen by newest modification time, which describes the
    filesystem rather than the data. It is right only while the run that wrote
    the file is the run reading it, and both callers below have a path where that
    is false: a fresh `git clone` stamps every artifact with the checkout time,
    and the daily pipeline carries on to the next step when a fetch fails, so
    there may be no fresh file at all.

    Every artifact here already carries the answer -- a camp list its
    `generated_at`, a bulletin its `report_date` -- so the ordering is a fact
    about the data. Reading them all costs a few hundred kilobytes and happens
    once per run.
    """

    return max(
        _candidates(path, pattern),
        key=lambda item: json.loads(item.read_text())[field],
    )


def _the_only_one(path: Path, pattern: str) -> Path:
    """The single artifact matching `pattern`, or a refusal.

    For a hand-chosen reference snapshot there is no such thing as the newest
    one. The UDISE roster is a 2021 community mirror pinned by its sha256; a
    second one appearing means someone deliberately added a different roster, and
    which of the two the matcher should use is their decision, not a coin toss
    over file timestamps. Say so and let them pass it explicitly.
    """

    matches = _candidates(path, pattern)
    if len(matches) > 1:
        names = ", ".join(item.name for item in matches)
        raise RuntimeError(
            f"{len(matches)} files match {path / pattern} and they have no order; "
            f"pass one explicitly ({names})"
        )
    return matches[0]


def _run_udise(args: argparse.Namespace) -> int:
    try:
        data_dir = Path(args.data_dir)
        if args.command == "ingest":
            result = ingest_assam_schools(source=args.source_url, data_dir=data_dir)
        else:
            camps_path = (
                Path(args.camps)
                if args.camps
                else _newest_by_field(
                    data_dir / "processed" / "district-camps", "*.json", "generated_at"
                )
            )
            schools_path = (
                Path(args.schools)
                if args.schools
                else _the_only_one(data_dir / "reference" / "udise", "assam-schools-*.csv")
            )
            result = match_camps_to_schools(
                camps_path=camps_path,
                schools_path=schools_path,
                data_dir=data_dir,
            )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        print(f"UDISE pipeline failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


def _run_gauges(args: argparse.Namespace) -> int:
    try:
        result = ingest_gauge_csv(
            source=args.gauge_source,
            data_dir=Path(args.data_dir),
            stale_after_hours=args.stale_after_hours,
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        print(f"gauge pipeline failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


def _run_cwc(args: argparse.Namespace) -> int:
    try:
        result = ingest_cwc_gauges(
            data_dir=Path(args.data_dir),
            stale_after_hours=args.stale_after_hours,
            backfill_hours=args.backfill_hours,
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        print(f"CWC gauge pipeline failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


def _run_flews(args: argparse.Namespace) -> int:
    try:
        result = ingest_public_flood_alerts(
            data_dir=Path(args.data_dir),
            stale_after_hours=args.stale_after_hours,
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        print(f"FLEWS pipeline failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


def _run_alerts(args: argparse.Namespace) -> int:
    try:
        result = run_alerts(
            data_dir=Path(args.data_dir),
            localities_path=Path(args.localities),
            cwc_snapshot=Path(args.cwc_snapshot) if args.cwc_snapshot else None,
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        print(f"alert pipeline failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


def _run_crowd(args: argparse.Namespace) -> int:
    """Phase 2 crowd-report and high-water-mark intake and open publication."""
    try:
        data_dir = Path(args.data_dir)
        if args.command == "ingest":
            result = ingest_crowd_inbox(
                inbox=Path(args.inbox),
                data_dir=data_dir,
                now=datetime.now(IST),
                delete_raw=not args.keep_raw,
            )
            # After ingest, publish the reconciled open dataset from the
            # accumulated series so the PWA and any open consumer can read
            # only aggregated, display-rule-respecting statements.
            result["published_open"] = publish_open_dataset(
                data_dir=data_dir,
                localities_path=Path(args.localities),
            )
            result["hwm_published"] = publish_high_water_mark_set(data_dir=data_dir)
        elif args.command == "publish":
            result = publish_open_dataset(
                data_dir=data_dir,
                localities_path=Path(args.localities),
                active_event=args.active_event,
            )
        elif args.command == "export":
            now = datetime.now(IST)
            since = now - timedelta(hours=args.since_hours)
            month = month_string(now)
            result = export_reports(
                SupabaseReportSource.from_env(),
                since=since,
                until=now,
                data_dir=data_dir,
                salt=load_month_salt(month, cache_dir=data_dir / "cache" / "crowd"),
                month=month,
                now=now,
            )
            # Reports that never reach an artifact help nobody, so publication
            # is part of the same command rather than a step to remember.
            result["published_open"] = publish_open_dataset(
                data_dir=data_dir,
                localities_path=Path(args.localities),
            )
        else:  # pragma: no cover - argparse enforces choices
            raise SystemExit(2)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        print(f"crowd pipeline failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


def _run_monitor(args: argparse.Namespace) -> int:
    try:
        data_dir = Path(args.data_dir)
        result = (
            record_success(
                data_dir=data_dir,
                run_id=args.run_id,
                run_origin=args.run_origin,
            )
            if args.command == "record"
            else monitor_status(data_dir=data_dir)
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        print(f"monitor failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


def _fetch_one(
    report_date: date,
    data_dir: Path,
    static_data_dir: Path,
    *,
    timeout_seconds: float,
    max_attempts: int,
    retry_backoff_seconds: float,
) -> dict[str, Any]:
    download = fetch_bulletin(
        report_date,
        timeout_seconds=timeout_seconds,
        max_attempts=max_attempts,
        retry_backoff_seconds=retry_backoff_seconds,
    )
    try:
        result = persist_bulletin(download, data_dir=data_dir)
    except BulletinParseError as exc:
        quarantine = quarantine_source_failure(
            download,
            data_dir=data_dir,
            static_data_dir=static_data_dir,
            error=exc,
        )
        return {
            "revision_id": quarantine["revision_id"],
            "impact_publication": quarantine,
        }
    result["impact_publication"] = publish_impact(
        Path(result["json"]),
        data_dir=data_dir,
        static_data_dir=static_data_dir,
    )
    return result


def _run_asdma(args: argparse.Namespace) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    data_dir = Path(args.data_dir)
    static_data_dir = Path(args.static_data_dir)
    started_at = datetime.now(IST).isoformat()
    attempts: list[dict[str, str]] = []

    try:
        if args.command == "publish":
            bulletin_path = (
                Path(args.bulletin)
                if args.bulletin
                else _newest_by_field(
                    data_dir / "processed" / "asdma", "*/*-extractor-v7.json", "report_date"
                )
            )
            result = publish_impact(
                bulletin_path,
                data_dir=data_dir,
                static_data_dir=static_data_dir,
                freshness_days=args.freshness_days,
            )
        elif args.command == "fetch":
            report_date = date.fromisoformat(args.date)
            result = _fetch_one(
                report_date,
                data_dir,
                static_data_dir,
                timeout_seconds=args.timeout,
                max_attempts=args.max_attempts,
                retry_backoff_seconds=args.retry_backoff,
            )
        else:
            today = datetime.now(IST).date()
            result = None
            for offset in range(args.lookback_days):
                candidate = today - timedelta(days=offset)
                try:
                    result = _fetch_one(
                        candidate,
                        data_dir,
                        static_data_dir,
                        timeout_seconds=args.timeout,
                        max_attempts=args.max_attempts,
                        retry_backoff_seconds=args.retry_backoff,
                    )
                    break
                except BulletinNotFound as exc:
                    attempts.append({"date": candidate.isoformat(), "outcome": "not_found"})
                    print(str(exc), file=sys.stderr)
            if result is None:
                raise BulletinNotFound(
                    f"no bulletin found in {args.lookback_days}-day lookback window"
                )

        publication = result.get("impact_publication", result)
        quarantined = publication.get("state") == "quarantined"
        status = {
            "schema_version": 1,
            "pipeline": "asdma_flood_bulletin",
            "status": "quarantined" if quarantined else "success",
            "started_at": started_at,
            "finished_at": datetime.now(IST).isoformat(),
            "attempts": attempts,
            "result": result,
        }
        _write_run_status(data_dir, status)
        print(json.dumps(result, indent=2, sort_keys=True))
        if quarantined:
            print(
                "ASDMA candidate quarantined; current impact pointer is unchanged.",
                file=sys.stderr,
            )
            return 1
        return 0
    except Exception as exc:
        status = {
            "schema_version": 1,
            "pipeline": "asdma_flood_bulletin",
            "status": "failed",
            "started_at": started_at,
            "finished_at": datetime.now(IST).isoformat(),
            "attempts": attempts,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }
        path = _write_run_status(data_dir, status)
        print(f"pipeline failed; status written to {path}: {exc}", file=sys.stderr)
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="axom-flood")
    sources = parser.add_subparsers(dest="source", required=True)
    asdma = sources.add_parser("asdma", help="ASDMA daily flood bulletins")
    commands = asdma.add_subparsers(dest="command", required=True)

    fetch = commands.add_parser("fetch", help="fetch one report date")
    fetch.add_argument("--date", required=True, help="report date in YYYY-MM-DD form")
    fetch.add_argument("--data-dir", default="data")
    fetch.add_argument("--static-data-dir", default="static/data")
    fetch.add_argument("--timeout", type=float, default=180)
    fetch.add_argument("--max-attempts", type=int, default=3)
    fetch.add_argument("--retry-backoff", type=float, default=2)

    latest = commands.add_parser("latest", help="fetch newest available report")
    latest.add_argument("--lookback-days", type=int, default=3)
    latest.add_argument("--data-dir", default="data")
    latest.add_argument("--static-data-dir", default="static/data")
    latest.add_argument("--timeout", type=float, default=180)
    latest.add_argument("--max-attempts", type=int, default=3)
    latest.add_argument("--retry-backoff", type=float, default=2)

    publish = commands.add_parser(
        "publish",
        help="validate and publish one retained ASDMA extractor artifact",
    )
    publish.add_argument("--bulletin")
    publish.add_argument("--data-dir", default="data")
    publish.add_argument("--static-data-dir", default="static/data")
    publish.add_argument("--freshness-days", type=int, default=DEFAULT_FRESHNESS_DAYS)

    camps = sources.add_parser("camps", help="district relief-camp source pipeline")
    camps.add_argument("--registry", default="config/assam-districts.json")
    camps.add_argument("--data-dir", default="data")
    camps.add_argument("--timeout", type=float, default=30)

    udise = sources.add_parser("udise", help="UDISE school ingest and camp matching")
    udise_commands = udise.add_subparsers(dest="command", required=True)
    udise_ingest = udise_commands.add_parser("ingest")
    udise_ingest.add_argument("--source-url", default=DEFAULT_SOURCE_URL)
    udise_ingest.add_argument("--data-dir", default="data")
    udise_match = udise_commands.add_parser("match")
    udise_match.add_argument("--camps")
    udise_match.add_argument("--schools")
    udise_match.add_argument("--data-dir", default="data")

    gauges = sources.add_parser("gauges", help="hourly gauge ingest")
    gauges.add_argument("--source", dest="gauge_source", required=True)
    gauges.add_argument("--data-dir", default="data")
    gauges.add_argument("--stale-after-hours", type=int, default=6)

    cwc = sources.add_parser("cwc", help="CWC Flood Forecasting System gauge feed")
    cwc.add_argument("--data-dir", default="data")
    cwc.add_argument("--stale-after-hours", type=int, default=6)
    cwc.add_argument(
        "--backfill-hours",
        type=int,
        default=0,
        help="seed local history per station so a trend is available on first run",
    )

    flews = sources.add_parser("flews", help="SMART AXOM/FLEWS public alert feed")
    flews.add_argument("--data-dir", default="data")
    flews.add_argument("--stale-after-hours", type=int, default=24)

    alerts = sources.add_parser("alerts", help="Phase 1 threshold alert engine")
    alerts.add_argument("--data-dir", default="data")
    alerts.add_argument("--localities", default="config/assam-localities.json")
    alerts.add_argument("--cwc-snapshot")

    crowd = sources.add_parser("crowd", help="Phase 2 crowd reports and high-water marks")
    crowd_commands = crowd.add_subparsers(dest="command", required=True)
    crowd_ingest = crowd_commands.add_parser(
        "ingest",
        help="ingest an inbox of submission JSON files and publish the open dataset",
    )
    crowd_ingest.add_argument("--inbox", default="data/inbox/crowd")
    crowd_ingest.add_argument("--data-dir", default="data")
    crowd_ingest.add_argument("--localities", default="config/assam-localities.json")
    crowd_ingest.add_argument(
        "--keep-raw",
        action="store_true",
        help=(
            "keep raw submission files after ingest "
            "(default: delete so full-precision GPS is never persisted)"
        ),
    )
    crowd_publish = crowd_commands.add_parser(
        "publish",
        help="re-publish the reconciled open dataset from the accumulated series",
    )
    crowd_publish.add_argument("--data-dir", default="data")
    crowd_publish.add_argument("--localities", default="config/assam-localities.json")
    crowd_publish.add_argument(
        "--active-event",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "override automatic fresh-CWC event detection; active mode hides "
            "reports older than 12 hours"
        ),
    )

    crowd_export = crowd_commands.add_parser(
        "export",
        help=(
            "pull reviewed reports from the reporting database into the crowd "
            "series, then re-publish the open dataset"
        ),
    )
    crowd_export.add_argument("--data-dir", default="data")
    crowd_export.add_argument("--localities", default="config/assam-localities.json")
    crowd_export.add_argument(
        "--since-hours",
        type=float,
        default=48.0,
        help=(
            "how far back to read. Overlapping windows are safe: ingest "
            "deduplicates by report id"
        ),
    )

    monitor = sources.add_parser("monitor", help="Phase 0 unattended-run evidence")
    monitor_commands = monitor.add_subparsers(dest="command", required=True)
    monitor_record = monitor_commands.add_parser("record")
    monitor_record.add_argument("--data-dir", default="data")
    monitor_record.add_argument("--run-id")
    monitor_record.add_argument(
        "--run-origin",
        choices=("schedule", "workflow_dispatch", "local"),
        default="local",
        help="only schedule records advance formal Phase 0 acceptance",
    )
    monitor_status_parser = monitor_commands.add_parser("status")
    monitor_status_parser.add_argument("--data-dir", default="data")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.source == "asdma":
        raise SystemExit(_run_asdma(args))
    if args.source == "camps":
        raise SystemExit(_run_camps(args))
    if args.source == "udise":
        raise SystemExit(_run_udise(args))
    if args.source == "gauges":
        raise SystemExit(_run_gauges(args))
    if args.source == "cwc":
        raise SystemExit(_run_cwc(args))
    if args.source == "flews":
        raise SystemExit(_run_flews(args))
    if args.source == "alerts":
        raise SystemExit(_run_alerts(args))
    if args.source == "crowd":
        raise SystemExit(_run_crowd(args))
    if args.source == "monitor":
        raise SystemExit(_run_monitor(args))
    raise SystemExit(2)


if __name__ == "__main__":
    main()
