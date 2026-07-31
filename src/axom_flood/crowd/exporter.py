"""Carry reviewed database reports into the existing crowd publication path.

The reporting database is an inbox, not the public record. Reports arrive there
from the website, Telegram and WhatsApp, and this module is the only thing that
moves them outward: it reads accepted rows through
``api.export_report_candidates``, maps each one onto the crowd submission shape
the Python pipeline already validates, and lets that pipeline anonymise,
append, and publish exactly as it does for any other submission.

Two properties are deliberate.

**No new privacy path.** Rows are pushed through ``ingest_crowd_submission``
rather than written to the series directly, so the closed key allow-list, the
coordinate rounding, the PII scan, and the device-hash salting all still apply.
A field added to the database later cannot leak into an artifact without first
being accepted by that allow-list.

**The reporter hash is hashed again.** The database stores an HMAC of the
sender keyed by the operator secret. Feeding it in as ``device_token`` means
the published ``device_hash`` is a hash of a hash under a *different* salt, so
a published record cannot be matched back to a database row without holding
both secrets.

Rejected, quarantined and duplicate rows never reach this module: the SQL
function filters to ``intake_status = 'accepted'``. Verification state is
carried through so the caller can decide what "reviewed enough to publish"
means without that policy being buried in SQL.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from .pipeline import IST, ingest_crowd_submission

#: Verification states that may be published. ``pending`` is included because
#: the public artifact is aggregate-only and applies its own quorum rule before
#: any statement is shown; excluding it would silence every report until a
#: moderator existed, and there is no moderation team yet.
PUBLISHABLE_VERIFICATION_STATES = frozenset({"pending", "corroborated"})

#: States that must never be published, listed explicitly so that a new state
#: added to the database fails loudly here instead of being silently exported.
WITHHELD_VERIFICATION_STATES = frozenset({"disputed", "rejected"})

REQUIRED_ROW_FIELDS = (
    "report_id",
    "observed_at",
    "locality_id",
    "depth_class",
    "reporter_hash",
    "verification_state",
    "longitude",
    "latitude",
)


class ReportSource(Protocol):
    """Anything that can hand back exportable rows for a time window.

    Kept as a protocol so the exporter is testable, and so a live Supabase
    client, a recorded fixture, and a local psql session are interchangeable.
    """

    def export_report_candidates(
        self, since: datetime, until: datetime
    ) -> Iterable[dict[str, Any]]: ...


class ExportError(RuntimeError):
    """A row could not be exported and the run must not silently continue."""


class ExportNotConfigured(ExportError):
    """No reporting database is configured, so there is nothing to export."""


class SupabaseReportSource:
    """Reads exportable rows from a hosted Supabase project.

    ``api.export_report_candidates`` is granted to ``service_role`` only, so
    this needs the service key and must never run in a browser. It is
    constructed from the environment rather than from arguments so a key is
    never passed on a command line where it would land in shell history.
    """

    def __init__(self, url: str, service_key: str, *, timeout: float = 30.0) -> None:
        if not url or not service_key:
            raise ExportNotConfigured("both a project URL and a service key are required")
        self.url = url.rstrip("/")
        self._service_key = service_key
        self._timeout = timeout

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> SupabaseReportSource:
        import os

        source = env if env is not None else dict(os.environ)
        url = source.get("SUPABASE_URL", "")
        key = source.get("SUPABASE_SERVICE_ROLE_KEY", "")
        if not url or not key:
            raise ExportNotConfigured(
                "set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY to export reports; "
                "no reporting database is configured yet"
            )
        return cls(url, key)

    def export_report_candidates(
        self, since: datetime, until: datetime
    ) -> Iterable[dict[str, Any]]:
        import httpx

        response = httpx.post(
            f"{self.url}/rest/v1/rpc/export_report_candidates",
            json={"p_since": since.isoformat(), "p_until": until.isoformat()},
            headers={
                "apikey": self._service_key,
                "authorization": f"Bearer {self._service_key}",
                "content-type": "application/json",
            },
            timeout=self._timeout,
        )
        if response.status_code >= 400:
            raise ExportError(
                f"export_report_candidates failed with HTTP {response.status_code}"
            )
        rows = response.json()
        if not isinstance(rows, list):
            raise ExportError("export_report_candidates did not return a list of rows")
        return rows


def _as_datetime(value: Any, field: str) -> datetime:
    if isinstance(value, datetime):
        moment = value
    elif isinstance(value, str):
        try:
            moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ExportError(f"{field} is not an ISO-8601 timestamp: {value!r}") from exc
    else:
        raise ExportError(f"{field} must be a timestamp, got {type(value).__name__}")
    if moment.tzinfo is None:
        raise ExportError(f"{field} must carry a timezone")
    return moment


def submission_from_row(row: dict[str, Any]) -> dict[str, Any]:
    """Map one exported database row onto a crowd submission.

    Only the keys the pipeline's allow-list accepts are produced. Report id,
    verification state and observation type stay behind: the first is the
    database's key rather than the series', and the other two are moderation
    metadata that the public artifact has no use for.
    """
    missing = [field for field in REQUIRED_ROW_FIELDS if field not in row]
    if missing:
        raise ExportError(f"exported row is missing {missing}")

    locality_id = row["locality_id"]
    if not locality_id:
        raise ExportError(
            "exported row has no locality; the SQL filter should have excluded it"
        )
    depth_class = row["depth_class"]
    if not depth_class:
        raise ExportError(
            f"report {row['report_id']} has no depth_class, so it cannot become a "
            "crowd report; observation-only rows need their own publication path"
        )
    reporter_hash = row["reporter_hash"]
    if not isinstance(reporter_hash, str) or len(reporter_hash) != 64:
        raise ExportError("reporter_hash must be the 64-character database HMAC")

    observed_at = _as_datetime(row["observed_at"], "observed_at")

    return {
        "latitude": float(row["latitude"]),
        "longitude": float(row["longitude"]),
        "depth_class": depth_class,
        # Hashed again under the publication salt; see the module docstring.
        "device_token": reporter_hash,
        "source": "app",
        "submitted_at": observed_at.astimezone(IST).isoformat(),
        "locality_id": locality_id,
        "report_id": str(row["report_id"]),
    }


def publishable(row: dict[str, Any]) -> bool:
    """Whether a row's verification state permits publication."""
    state = row.get("verification_state")
    if state in PUBLISHABLE_VERIFICATION_STATES:
        return True
    if state in WITHHELD_VERIFICATION_STATES:
        return False
    raise ExportError(
        f"unknown verification_state {state!r}; add it to either "
        "PUBLISHABLE_VERIFICATION_STATES or WITHHELD_VERIFICATION_STATES "
        "before exporting"
    )


def export_reports(
    source: ReportSource,
    *,
    since: datetime,
    until: datetime,
    data_dir: Path,
    salt: bytes,
    month: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Ingest every publishable report in ``[since, until)``.

    Returns counts rather than records so a scheduled run can be logged without
    writing report contents to a log file. Ingestion is append-and-deduplicate,
    so re-running an overlapping window is safe and reports an ``appended``
    count of zero for rows already present.
    """
    if until <= since:
        raise ExportError("export window must end after it starts")

    rows: Sequence[dict[str, Any]] = list(source.export_report_candidates(since, until))
    considered = 0
    withheld = 0
    appended = 0
    duplicates = 0
    for row in rows:
        considered += 1
        if not publishable(row):
            withheld += 1
            continue
        result = ingest_crowd_submission(
            submission_from_row(row),
            data_dir=data_dir,
            salt=salt,
            month=month,
            now=now,
        )
        if result["appended"]:
            appended += 1
        else:
            duplicates += 1

    return {
        "window_start": since.isoformat(),
        "window_end": until.isoformat(),
        "rows_considered": considered,
        "reports_appended": appended,
        "reports_already_present": duplicates,
        "reports_withheld": withheld,
    }
