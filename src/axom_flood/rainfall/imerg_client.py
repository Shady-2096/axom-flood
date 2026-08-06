"""Discovery and download for NASA IMERG half-hourly granules.

Workstream C of the local-accuracy master plan, second half. The parser in
`imerg.py` turns a normalized payload into rates; `zonal.py` turns a grid into a
circle number. This is the part in between that goes and gets the grid.

Disabled until somebody turns it on
-----------------------------------

IMERG needs an Earthdata Login. This client cannot make a live request unless it
is constructed with `enabled=True` *and* handed a token, and it says which of the
two is missing. Without both it raises rather than returning an empty result,
because an empty result is indistinguishable from "it did not rain".

Latency is measured, never assumed
----------------------------------

NASA attributes roughly four-hour availability to the **Early** run. The Late run
is the better estimate and arrives later; an earlier handoff to this project
mistakenly claimed four hours for Late, and the fix is not to write a better
number down but to stop writing one down at all. Every download records when the
archive says the granule was published and how far behind its own observation
window that was. `ImergDownload.observed_latency_hours` is that measurement.
`IMERG_POLICIES[...].typical_latency_hours` stays a documented expectation to
compare against, and nothing in the pipeline is allowed to treat it as fact.

⚠️ The archive path convention below is written from NASA's published naming and
has **not** been confirmed against the live archive**,** because no credentials
exist yet. `scripts/smoke_imerg.py` is the one command that confirms it. Until
that has been run against a real account, treat granule URLs as unverified —
the fixtures prove the parsing and the arithmetic, not the path.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from .imd import SourceDisabledError
from .imerg import IMERG_POLICIES, ImergRun
from .provenance import SourceRevision, parse_aware_datetime, require_aware

#: GES DISC is the archive that serves the half-hourly Level-3 products.
GES_DISC_BASE = "https://gpm1.gesdisc.eosdis.nasa.gov/data"

EARTHDATA_LOGIN_URL = "https://urs.earthdata.nasa.gov/"
EARTHDATA_REGISTRATION_URL = "https://urs.earthdata.nasa.gov/users/new"

#: IMERG V07 ships revised letters (V07A, V07B, …) as the record is reprocessed.
#: Pinned rather than guessed at runtime, and overridable, so a revision is a
#: recorded decision instead of a silent change in what was downloaded.
#:
#: V07C confirmed against the live archive on 2026-08-07 — the whole Late-run
#: directory for that day carried it, and V07B (the letter this was written with)
#: 404s. Every other character of the filename convention below was right.
#: When this letter changes again the symptom is a 404 on every granule, which
#: `scripts/build_rainfall.py` reports as "not published" rather than as an error;
#: check a directory listing before believing the archive is simply behind.
DEFAULT_VERSION_SUFFIX = "V07C"

#: Half-hourly. A granule covers [start, start + 30 minutes).
GRANULE_MINUTES = 30

_RUN_FILE_LETTER = {ImergRun.EARLY: "E", ImergRun.LATE: "L"}


class ImergCredentialsMissing(RuntimeError):
    """The client was enabled without the Earthdata token it needs."""

    def __init__(self) -> None:
        super().__init__(
            "IMERG access is enabled but no Earthdata bearer token was supplied; "
            f"register at {EARTHDATA_REGISTRATION_URL} and pass the token"
        )


class ImergAuthError(RuntimeError):
    """Earthdata rejected the credentials, or the application is not authorised."""

    def __init__(self, *, status_code: int) -> None:
        self.status_code = status_code
        super().__init__(
            f"Earthdata returned HTTP {status_code}. A valid token is not enough: "
            "the GES DISC application must also be authorised once, under "
            f"{EARTHDATA_LOGIN_URL} Applications → Authorized Apps"
        )


@dataclass(frozen=True, slots=True)
class ImergGranule:
    """One half-hour of one run, and where it lives."""

    run: ImergRun
    interval_start: datetime
    interval_end: datetime
    filename: str
    url: str
    version_suffix: str

    @property
    def product_short_name(self) -> str:
        return IMERG_POLICIES[self.run].product_short_name

    def as_dict(self) -> dict[str, Any]:
        return {
            "run": self.run.value,
            "product_short_name": self.product_short_name,
            "interval_start": self.interval_start.isoformat(),
            "interval_end": self.interval_end.isoformat(),
            "filename": self.filename,
            "url": self.url,
            "version_suffix": self.version_suffix,
            "path_verified_against_live_archive": False,
        }


@dataclass(frozen=True, slots=True)
class ImergDownload:
    """Bytes, their identity, and what the archive said about when they appeared."""

    granule: ImergGranule
    content: bytes
    revision: SourceRevision
    etag: str | None
    published_at: datetime | None
    published_at_source: str
    observed_latency_hours: float | None

    def as_dict(self) -> dict[str, Any]:
        policy = IMERG_POLICIES[self.granule.run]
        return {
            "granule": self.granule.as_dict(),
            "revision": self.revision.as_dict(),
            "etag": self.etag,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "published_at_source": self.published_at_source,
            "observed_latency_hours": self.observed_latency_hours,
            "documented_typical_latency_hours": policy.typical_latency_hours,
            "latency_note": (
                "observed_latency_hours is measured from this download. The "
                "documented figure is an expectation to compare against and is "
                "never substituted for a measurement."
            ),
        }


def granule_for(
    moment: datetime,
    *,
    run: ImergRun,
    version_suffix: str = DEFAULT_VERSION_SUFFIX,
    archive_base: str = GES_DISC_BASE,
) -> ImergGranule:
    """Name the granule covering `moment`, snapping down to its half hour."""

    require_aware(moment, "moment")
    moment = moment.astimezone(UTC)
    start = moment.replace(
        minute=0 if moment.minute < GRANULE_MINUTES else GRANULE_MINUTES,
        second=0,
        microsecond=0,
    )
    end = start + timedelta(minutes=GRANULE_MINUTES)
    # The archive labels the end second as :29 or :59, one second short of the
    # next granule, while the interval itself is half-open. Both appear below on
    # purpose: the filename gets the label, the dataclass gets the real bound.
    label_end = end - timedelta(seconds=1)
    minutes_index = start.hour * 60 + start.minute

    letter = _RUN_FILE_LETTER[run]
    filename = (
        f"3B-HHR-{letter}.MS.MRG.3IMERG."
        f"{start:%Y%m%d}-S{start:%H%M%S}-E{label_end:%H%M%S}."
        f"{minutes_index:04d}.{version_suffix}.HDF5"
    )
    product = IMERG_POLICIES[run].product_short_name
    url = (
        f"{archive_base.rstrip('/')}/GPM_L3/{product}/"
        f"{start:%Y}/{start.timetuple().tm_yday:03d}/{filename}"
    )
    return ImergGranule(
        run=run,
        interval_start=start,
        interval_end=end,
        filename=filename,
        url=url,
        version_suffix=version_suffix,
    )


def discover_granules(
    *,
    run: ImergRun,
    window_start: datetime,
    window_end: datetime,
    version_suffix: str = DEFAULT_VERSION_SUFFIX,
    archive_base: str = GES_DISC_BASE,
) -> list[ImergGranule]:
    """Every granule needed to cover a window, with no gaps and no overlap.

    A rainfall accumulation is only honest if it is built from a continuous run
    of granules, so this returns the whole set or the caller has a hole it can
    see. `accumulate_imerg_cell` refuses gaps downstream as well; this is the
    step that makes the gap visible before anything is downloaded.
    """

    require_aware(window_start, "window_start")
    require_aware(window_end, "window_end")
    if window_end <= window_start:
        raise ValueError("window_end must be after window_start")

    granules: list[ImergGranule] = []
    cursor = granule_for(
        window_start, run=run, version_suffix=version_suffix, archive_base=archive_base
    )
    while cursor.interval_start < window_end:
        granules.append(cursor)
        cursor = granule_for(
            cursor.interval_end,
            run=run,
            version_suffix=version_suffix,
            archive_base=archive_base,
        )
    return granules


class ImergClient:
    """Narrow client that cannot reach NASA unless enabled and given a token."""

    def __init__(
        self,
        *,
        enabled: bool = False,
        bearer_token: str | None = None,
        timeout: float = 120,
        transport: httpx.BaseTransport | None = None,
        archive_base: str = GES_DISC_BASE,
        version_suffix: str = DEFAULT_VERSION_SUFFIX,
    ) -> None:
        self.enabled = enabled
        self.archive_base = archive_base
        self.version_suffix = version_suffix
        self._token = (bearer_token or "").strip() or None
        self._client = httpx.Client(
            timeout=timeout, transport=transport, follow_redirects=True
        )

    def __enter__(self) -> ImergClient:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def access_state(self) -> dict[str, Any]:
        """Everything an operator needs to see why this is or is not working."""
        return {
            "source_id": "nasa-gpm-imerg",
            "enabled": self.enabled,
            "has_token": self._token is not None,
            "access_mode": "earthdata_login_bearer_token",
            "registration_url": EARTHDATA_REGISTRATION_URL,
            "archive_base": self.archive_base,
            "version_suffix": self.version_suffix,
            "ready": self.enabled and self._token is not None,
            "path_verified_against_live_archive": False,
        }

    def check_configuration(self) -> None:
        """Raise the specific reason a live call would fail, before making one."""
        if not self.enabled:
            raise SourceDisabledError(
                "IMERG live access is disabled; enable it only once an Earthdata "
                "account exists and its token is configured"
            )
        if self._token is None:
            raise ImergCredentialsMissing()

    def get(self, url: str) -> httpx.Response:
        """One authenticated GET, with Earthdata's two failure modes named.

        Public because the OPeNDAP subset path and the smoke test's `--describe`
        step need the same auth handling against URLs that are not granule
        downloads.
        """

        self.check_configuration()
        response = self._client.get(url, headers={"Authorization": f"Bearer {self._token}"})
        if response.status_code in {401, 403}:
            raise ImergAuthError(status_code=response.status_code)
        response.raise_for_status()
        return response

    def fetch_granule(
        self,
        granule: ImergGranule,
        *,
        fetched_at: datetime,
    ) -> ImergDownload:
        require_aware(fetched_at, "fetched_at")
        response = self.get(granule.url)
        content = response.content
        if not content:
            raise ValueError(f"{granule.filename} returned an empty body")

        published_at, published_source = publication_time(response)
        latency = None
        if published_at is not None:
            delta = published_at - granule.interval_end
            latency = round(delta.total_seconds() / 3600, 3)

        return ImergDownload(
            granule=granule,
            content=content,
            revision=SourceRevision.capture(
                content,
                source_id="nasa-gpm-imerg",
                source_url=str(response.url),
                fetched_at=fetched_at,
                media_type=response.headers.get("content-type", "application/x-hdf5")
                .split(";", 1)[0]
                or "application/x-hdf5",
            ),
            etag=response.headers.get("etag"),
            published_at=published_at,
            published_at_source=published_source,
            observed_latency_hours=latency,
        )


def publication_time(response: httpx.Response) -> tuple[datetime | None, str]:
    """When the archive says these bytes appeared, and how we know.

    `Last-Modified` is the archive's own statement and is preferred. When it is
    absent the download time is *not* silently substituted — that would report
    our own lateness as NASA's — so the source is named and the latency it
    implies is marked as an upper bound by the caller.
    """

    raw = response.headers.get("last-modified")
    if raw:
        try:
            parsed = datetime.strptime(raw, "%a, %d %b %Y %H:%M:%S %Z")
            return parsed.replace(tzinfo=UTC), "archive_last_modified"
        except ValueError:
            pass
    iso = response.headers.get("x-published-at")
    if iso:
        try:
            return parse_aware_datetime(iso, "x-published-at"), "archive_header"
        except ValueError:
            pass
    return None, "unavailable"
