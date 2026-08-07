"""Turn IMERG half-hours into one published rainfall sentence per circle.

Run with:
  uv run python scripts/build_rainfall.py --plan     # no network, no account
  uv run python scripts/build_rainfall.py            # needs EARTHDATA_TOKEN
  uv run python scripts/build_rainfall.py --publish  # …and write into static/data

Workstream C, end to end. Every piece it uses already existed and none of them
were joined up: `build_rainfall_zones.py` says which grid cells belong to which
circle, `subset.py` fetches those cells from NASA, `windows.py` totals them over
the five windows, and `sentence.py` writes the English. This is the script that
runs them in order and publishes the result.

Three things it will not do
---------------------------

- **Fill a hole.** A granule that has not been published yet is left out, and the
  windows that needed it come back unavailable with a reason. Nothing is carried
  forward from the previous half hour.
- **Mix runs.** Early and Late are separate products. One invocation builds one
  run, and the run is named in the artifact.
- **Publish a partial rebuild.** The published file is written only after every
  circle has been computed, so a run that dies halfway leaves the live site on
  the previous artifact rather than on half of this one.

`--plan` needs no credentials. It prints the granules, the box, and the first
URL, which is enough to check the shape of a run before an account exists.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from axom_flood.rainfall.imerg import (  # noqa: E402
    IMERG_POLICIES,
    ImergRun,
    parse_imerg_observations,
)
from axom_flood.rainfall.imerg_client import (  # noqa: E402
    PATH_VERIFIED_AGAINST_LIVE_ARCHIVE,
    ImergAuthError,
    ImergClient,
    ImergCredentialsMissing,
    ImergRequestTimeout,
    discover_granules,
)
from axom_flood.rainfall.sentence import (  # noqa: E402
    ATTRIBUTION,
    ESTIMATE_NOTE,
    HEDGE,
    STALE_MARGIN_HOURS,
    UNAVAILABLE_TEXT,
    describe_circle_rainfall,
)
from axom_flood.rainfall.subset import (  # noqa: E402
    GridBox,
    SubsetError,
    fetch_subset,
    subset_request,
)
from axom_flood.rainfall.windows import RAINFALL_WINDOW_HOURS, accumulate_windows  # noqa: E402
from axom_flood.rainfall.zonal import CellWeight, ZonalWeights  # noqa: E402

ZONES_DIR = ROOT / "data" / "processed" / "rainfall-zones"
SUBSET_DIR = ROOT / "data" / "processed" / "imerg-subsets"
OUT_DIR = ROOT / "data" / "processed" / "rainfall"
STATIC_DIR = ROOT / "static" / "data"
POINTER = STATIC_DIR / "rainfall-current.json"

#: The longest window decides how far back to fetch. Everything shorter is a
#: subset of the same series, so nothing is downloaded twice.
LOOKBACK_HOURS = max(RAINFALL_WINDOW_HOURS)

_GRANULE_MINUTES = 30

#: How many half hours to fetch at once.
#:
#: Started at 6 and was lowered to 2 after the first concurrent run stalled: six
#: requests in flight for fifteen minutes, nothing downloaded, nothing raised.
#: The cause was never proved — either GES DISC serialises OPeNDAP requests per
#: user, or it was trickling responses under a read timeout that restarts on
#: every chunk. `ImergClient` now measures each request and fails on a deadline,
#: so the next run says which. Two is the conservative setting to learn from; it
#: is also a courtesy limit on a shared public archive, not a tuning knob to
#: turn up until something breaks.
FETCH_WORKERS = int(os.environ.get("RAINFALL_FETCH_WORKERS", "2"))


def newest_zones() -> tuple[Path, dict[str, Any]]:
    candidates = sorted(ZONES_DIR.glob("*.json"))
    if not candidates:
        raise SystemExit(
            "no zone weights found; run scripts/build_rainfall_zones.py first"
        )
    newest = max(candidates, key=lambda path: path.stat().st_mtime)
    return newest, json.loads(newest.read_text())


def weights_from_zone(zone: dict[str, Any], cell_degrees: float) -> ZonalWeights:
    return ZonalWeights(
        locality_id=zone["locality_id"],
        cell_degrees=cell_degrees,
        weights=tuple(
            CellWeight(
                grid_cell_id=cell["grid_cell_id"],
                longitude=cell["longitude"],
                latitude=cell["latitude"],
                share=cell["share"],
                area_sq_km=cell["area_sq_km"],
            )
            for cell in zone["cells"]
        ),
        circle_area_sq_km=zone["circle_area_sq_km"],
        boundary_sha256=zone["boundary_sha256"],
    )


def latest_expected_as_of(run: ImergRun, now: datetime) -> datetime:
    """The newest window end the archive could plausibly have published.

    Built from the run's documented latency, floored to a half hour. It is an
    expectation about the archive, not a claim about the data: if the granule is
    not there, the windows ending at this moment are refused, which is exactly
    the intended outcome.
    """

    edge = now - timedelta(hours=IMERG_POLICIES[run].typical_latency_hours)
    return edge.replace(
        minute=0 if edge.minute < _GRANULE_MINUTES else _GRANULE_MINUTES,
        second=0,
        microsecond=0,
    )


def resolve_as_of(
    client: ImergClient,
    *,
    run: ImergRun,
    box: GridBox,
    expected: datetime,
    max_steps: int = 48,
) -> tuple[datetime, int]:
    """Walk back from the expected newest half hour to one that really exists.

    The documented latency is an expectation and lands slightly ahead of the
    archive even on a healthy day. Ending every window at a granule that has not
    been published yet would refuse all five windows for every circle, every run
    — an honest answer to a question nobody asked, since the newest *published*
    half hour is a perfectly good window end and the copy already names the hour
    it ended.

    Probes the OPeNDAP metadata document, which is a few kilobytes, rather than
    the data. Returns the window end and how many half hours it had to give up,
    so a growing number is visible as the archive falling behind.
    """

    for step in range(max_steps):
        candidate = expected - timedelta(minutes=_GRANULE_MINUTES * step)
        granule = discover_granules(
            run=run,
            window_start=candidate - timedelta(minutes=_GRANULE_MINUTES),
            window_end=candidate,
        )[0]
        try:
            client.get(subset_request(granule, box).describe_url)
        except httpx.HTTPStatusError as error:
            if error.response.status_code == 404:
                continue
            raise
        return candidate, step
    raise SystemExit(
        f"no {run.value} granule found in the {max_steps // 2} hours before "
        f"{expected:%Y-%m-%d %H:%M} UTC; the archive is further behind than any "
        "window this pipeline publishes"
    )


def cached_subset_path(run: ImergRun, filename: str) -> Path:
    return SUBSET_DIR / run.value / f"{filename}.json"


def store_subset(path: Path, content: bytes) -> None:
    """Write a subset once. A changed payload under the same name is an event.

    Same granule filename, different numbers, means NASA reprocessed the record
    without changing the version letter in the name. That is worth stopping for
    rather than silently adopting.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != content:
            raise SystemExit(
                f"{path.relative_to(ROOT)} already exists with different contents; "
                "the archive changed a granule under a name it had already used"
            )
        return
    path.write_bytes(content)


def _timed_fetch(
    client: ImergClient,
    request: Any,
    *,
    fetched_at: datetime,
    keep_cell_ids: set[str],
) -> tuple[Any, float]:
    """`fetch_subset` with a stopwatch on it.

    The per-request wall time is the number that tells an operator whether the
    archive is slow, whether concurrency is helping, or whether requests are
    being queued behind each other — none of which was visible when this only
    reported a total.
    """

    started = time.monotonic()
    download = fetch_subset(
        client, request, fetched_at=fetched_at, keep_cell_ids=keep_cell_ids
    )
    return download, time.monotonic() - started


def collect_observations(
    *,
    client: ImergClient | None,
    run: ImergRun,
    as_of: datetime,
    box: GridBox,
    keep_cells: set[str],
    fetched_at: datetime,
    verbose: bool,
) -> tuple[list[Any], dict[str, Any]]:
    """Every half hour we could get, plus a record of the ones we could not."""

    granules = discover_granules(
        run=run, window_start=as_of - timedelta(hours=LOOKBACK_HOURS), window_end=as_of
    )
    observations: list[Any] = []
    absent: list[str] = []
    latencies: list[float] = []

    missing = [
        granule
        for granule in granules
        if not cached_subset_path(run, granule.filename).exists()
    ]
    from_cache = len(granules) - len(missing)
    downloaded = 0

    if missing and client is None:
        absent.extend(granule.filename for granule in missing)
        missing = []

    fetch_seconds: list[float] = []
    if missing:
        # Measured at about 40 seconds per half hour: GES DISC cuts the box out
        # of a global HDF5 file for every request, and that dominates. Serially
        # a cold 72-hour window is an hour and a half, which is longer than the
        # two hours between runs leaves room for.
        #
        # Modest on purpose. This is a shared public archive, and the point is
        # to stop waiting on one round trip at a time, not to pull as hard as
        # the server will allow.
        started = time.monotonic()
        if verbose:
            print(f"fetching       {len(missing)} half hours, {FETCH_WORKERS} at a time")
        with ThreadPoolExecutor(max_workers=FETCH_WORKERS) as pool:
            futures = {
                pool.submit(
                    _timed_fetch,
                    client,
                    subset_request(granule, box),
                    fetched_at=fetched_at,
                    keep_cell_ids=keep_cells,
                ): granule
                for granule in missing
            }
            for done, future in enumerate(as_completed(futures), start=1):
                granule = futures[future]
                try:
                    download, seconds = future.result()
                except httpx.HTTPStatusError as error:
                    if error.response.status_code == 404:
                        absent.append(granule.filename)
                        continue
                    raise
                except ImergRequestTimeout as error:
                    # Loud on purpose. The failure this replaces was a run that
                    # sat for fifteen minutes and then reported success with no
                    # new files, which is the worst possible way to be wrong.
                    raise SystemExit(
                        f"{granule.filename}: {error}\n"
                        f"  {downloaded} of {len(missing)} half hours had been "
                        f"downloaded when this stalled. Cached subsets are kept, "
                        f"so re-running resumes. If this repeats, try "
                        f"RAINFALL_FETCH_WORKERS=1."
                    ) from error
                except SubsetError as error:
                    raise SystemExit(f"{granule.filename}: {error}") from error
                store_subset(cached_subset_path(run, granule.filename), download.content)
                downloaded += 1
                fetch_seconds.append(seconds)
                if download.observed_latency_hours is not None:
                    latencies.append(download.observed_latency_hours)
                # Every tenth, not every twenty-fourth. A cold 72-hour window is
                # 144 granules at roughly 40 seconds each, and a line every 16
                # minutes is indistinguishable from a hung process.
                if verbose and done % 10 == 0:
                    rate = (time.monotonic() - started) / done
                    left = (len(missing) - done) * rate
                    print(
                        f"  … {done}/{len(missing)}  "
                        f"{seconds:.0f}s last, {rate:.0f}s each, "
                        f"~{left / 60:.0f} min left"
                    )
        if verbose and fetch_seconds:
            ordered = sorted(fetch_seconds)
            print(
                f"request times  fastest {ordered[0]:.0f}s, "
                f"median {ordered[len(ordered) // 2]:.0f}s, "
                f"slowest {ordered[-1]:.0f}s, "
                f"{time.monotonic() - started:.0f}s of wall clock for "
                f"{len(fetch_seconds)} at {FETCH_WORKERS} at a time"
            )

    # Parsed in granule order, from disk, after every fetch has settled. The
    # windows care about a continuous series, and reading it back in one pass
    # keeps that ordering independent of which download happened to finish first.
    for granule in granules:
        cached = cached_subset_path(run, granule.filename)
        if not cached.exists():
            continue
        content = cached.read_bytes()
        # The URL that travels with the observations is the one the payload
        # recorded when it was fetched, not the path it happens to be cached at.
        # A cached file re-read a week later must still point at NASA.
        observations.extend(
            parse_imerg_observations(
                content,
                fetched_at=fetched_at,
                source_url=json.loads(content)["source_url"],
            )
        )

    return observations, {
        "granules_expected": len(granules),
        "granules_present": from_cache + downloaded,
        "granules_from_cache": from_cache,
        "granules_downloaded": downloaded,
        "granules_absent": len(absent),
        "first_absent": absent[:5],
        "observed_latency_hours": (
            round(sum(latencies) / len(latencies), 3) if latencies else None
        ),
        # How long the archive took, kept with the numbers it produced. A run
        # that took four times as long as the last one is the first sign that
        # the two-hourly schedule is about to stop fitting, and it should be
        # readable from the artifact rather than from a lost terminal.
        "fetch_workers": FETCH_WORKERS if downloaded else None,
        "median_request_seconds": (
            round(sorted(fetch_seconds)[len(fetch_seconds) // 2], 1)
            if fetch_seconds
            else None
        ),
        "slowest_request_seconds": (
            round(max(fetch_seconds), 1) if fetch_seconds else None
        ),
    }


def build_document(
    *,
    zones: dict[str, Any],
    zones_path: Path,
    observations: list[Any],
    coverage: dict[str, Any],
    run: ImergRun,
    as_of: datetime,
    now: datetime,
) -> dict[str, Any]:
    cell_degrees = zones["cell_degrees"]
    by_cell: dict[str, list[Any]] = {}
    for observation in observations:
        by_cell.setdefault(observation.grid_cell_id, []).append(observation)

    circles = []
    counts = {"estimate": 0, "stale_estimate": 0, "unavailable": 0}
    for zone in zones["zones"]:
        weights = weights_from_zone(zone, cell_degrees)
        boundary = zone["boundary"]
        mine = [
            observation
            for cell_id in weights.cell_ids
            for observation in by_cell.get(cell_id, ())
        ]
        place_name = f"{boundary['revenue_circle']} circle"

        if not mine:
            circles.append(
                {
                    "locality_id": weights.locality_id,
                    "revenue_circle": boundary["revenue_circle"],
                    "district": boundary["district"],
                    "status": "unavailable",
                    "unavailable_reason": "missing_cells",
                    "window_hours": None,
                    "total_precipitation_mm": None,
                    "windows": {},
                    "headline": (
                        f"No satellite rainfall estimate is available for "
                        f"{place_name}. "
                        f"{UNAVAILABLE_TEXT['missing_cells']}"
                    ),
                }
            )
            counts["unavailable"] += 1
            continue

        rainfall = accumulate_windows(weights, mine, as_of=as_of)
        described = describe_circle_rainfall(rainfall, now=now, place_name=place_name)
        counts[described["status"]] = counts.get(described["status"], 0) + 1
        circles.append(
            {
                "locality_id": weights.locality_id,
                "revenue_circle": boundary["revenue_circle"],
                "district": boundary["district"],
                "status": described["status"],
                "unavailable_reason": described["unavailable_reason"],
                "window_hours": described["window_hours"],
                "total_precipitation_mm": described["total_precipitation_mm"],
                "windows": {
                    str(window.hours): (
                        None
                        if not window.available
                        else round(float(window.total_mm), 1)
                    )
                    for window in rainfall.windows
                },
                "window_unavailable_reasons": {
                    str(window.hours): window.unavailable_reason
                    for window in rainfall.windows
                    if not window.available
                },
                "headline": described["headline"],
                "stale_headline": described.get("stale_headline"),
            }
        )

    policy = IMERG_POLICIES[run]
    return {
        "schema_version": 1,
        "record": "circle_rainfall_estimates",
        "run": run.value,
        "as_of": as_of.isoformat(),
        "window_hours": list(RAINFALL_WINDOW_HOURS),
        "source": {
            "attribution": f"{ATTRIBUTION} ({run.value} run)",
            "product_short_name": policy.product_short_name,
            "product_version": "07",
            "documented_typical_latency_hours": policy.typical_latency_hours,
            "stale_after_hours": policy.typical_latency_hours + STALE_MARGIN_HOURS,
            "use_note": policy.use_note,
            "path_verified_against_live_archive": PATH_VERIFIED_AGAINST_LIVE_ARCHIVE,
        },
        "shared_text": {
            "estimate_note": ESTIMATE_NOTE,
            "hedge": HEDGE,
            "unavailable": dict(UNAVAILABLE_TEXT),
        },
        "coverage": coverage,
        "provenance": {
            "zone_weights": str(zones_path.relative_to(ROOT)),
            "boundary_review": zones["provenance"]["boundary_review"],
            "boundary_sha256": zones["provenance"]["boundary_sha256"],
            "built_by": "scripts/build_rainfall.py",
            "aggregation": "area_weighted_mean_over_circle",
            "note": (
                "Circles without an analysis-grade boundary are absent from this "
                "file entirely. Absence is not a rainfall of zero."
            ),
        },
        "attribution": zones.get("attribution"),
        "totals": {"circles": len(circles), **counts},
        "circles": circles,
    }


def publish(document: dict[str, Any], *, digest: str, generated_at: datetime) -> Path:
    """Write the digest-named artifact and move the pointer to it.

    The published body deliberately carries no build timestamp. Two runs that
    compute the same rainfall then produce byte-identical files under the same
    digest, so a rebuild is a no-op instead of a new download for every phone.
    When the run happened lives in the pointer, which is mutable by design.
    """

    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    target = STATIC_DIR / f"rainfall-{digest}.json"
    body = json.dumps(document, separators=(",", ":"), sort_keys=True).encode() + b"\n"
    if target.exists() and target.read_bytes() != body:
        raise SystemExit(f"refusing to overwrite immutable artifact: {target}")
    if not target.exists():
        target.write_bytes(body)
    POINTER.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "rainfall_url": f"data/{target.name}",
                "revision_id": digest,
                "run": document["run"],
                "as_of": document["as_of"],
                "generated_at": generated_at.isoformat(),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    return target


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", action="store_true", help="no network; print the run")
    parser.add_argument("--run", choices=[item.value for item in ImergRun], default="late")
    parser.add_argument("--publish", action="store_true", help="write into static/data")
    parser.add_argument(
        "--as-of",
        default=None,
        help="ISO end of every window; defaults to the run's expected newest half hour",
    )
    args = parser.parse_args()

    run = ImergRun(args.run)
    now = datetime.now(UTC)
    expected = latest_expected_as_of(run, now)
    as_of = (
        datetime.fromisoformat(args.as_of).astimezone(UTC) if args.as_of else expected
    )

    zones_path, zones = newest_zones()
    keep_cells = {
        cell["grid_cell_id"] for zone in zones["zones"] for cell in zone["cells"]
    }
    box = GridBox.around_cells(sorted(keep_cells), cell_degrees=zones["cell_degrees"])

    print(f"run            {run.value} ({IMERG_POLICIES[run].product_short_name})")
    print(f"expected end   {expected:%Y-%m-%d %H:%M} UTC (documented latency)")
    print(f"reaching back  {LOOKBACK_HOURS} h ({LOOKBACK_HOURS * 2} half hours)")
    print(f"circles        {zones['totals']['circles']} over {len(keep_cells)} cells")
    print(
        f"box            {box.west:.1f}–{box.east:.1f}E, {box.south:.1f}–{box.north:.1f}N"
    )

    if args.plan:
        first = discover_granules(
            run=run,
            window_start=as_of - timedelta(hours=LOOKBACK_HOURS),
            window_end=as_of,
        )[0]
        request = subset_request(first, box)
        print(f"cells asked    {request.cell_count} per half hour")
        print(f"first url      {request.url}")
        print("\nplan only: nothing was requested.")
        return 0

    client: ImergClient | None = None
    token = os.environ.get("EARTHDATA_TOKEN", "")
    try:
        client = ImergClient(enabled=True, bearer_token=token)
        client.check_configuration()
    except ImergCredentialsMissing as error:
        print(f"\nnot configured: {error}")
        return 2

    if not args.as_of:
        try:
            as_of, gave_up = resolve_as_of(client, run=run, box=box, expected=expected)
        except ImergAuthError as error:
            client.close()
            print(f"\nrejected: {error}")
            return 3
        behind = (now - as_of).total_seconds() / 3600
        print(
            f"windows end    {as_of:%Y-%m-%d %H:%M} UTC — {behind:.1f} h behind now, "
            f"{gave_up} half hours past the documented expectation"
        )
    else:
        print(f"windows end    {as_of:%Y-%m-%d %H:%M} UTC (given)")

    try:
        observations, coverage = collect_observations(
            client=client,
            run=run,
            as_of=as_of,
            box=box,
            keep_cells=keep_cells,
            fetched_at=now,
            verbose=True,
        )
    except ImergAuthError as error:
        print(f"\nrejected: {error}")
        return 3
    finally:
        client.close()

    print(
        f"half hours     {coverage['granules_present']}/{coverage['granules_expected']} "
        f"({coverage['granules_downloaded']} downloaded, "
        f"{coverage['granules_from_cache']} cached, "
        f"{coverage['granules_absent']} not published)"
    )

    document = build_document(
        zones=zones,
        zones_path=zones_path,
        observations=observations,
        coverage=coverage,
        run=run,
        as_of=as_of,
        now=now,
    )
    totals = document["totals"]
    print(
        f"circles        {totals.get('estimate', 0)} with an estimate, "
        f"{totals.get('stale_estimate', 0)} stale, "
        f"{totals.get('unavailable', 0)} unavailable"
    )

    body = json.dumps(document, indent=2, sort_keys=True).encode()
    digest = sha256(body).hexdigest()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    target = OUT_DIR / f"{digest}.json"
    if not target.exists():
        target.write_text(
            json.dumps({**document, "generated_at": now.isoformat()}, indent=2, sort_keys=True)
            + "\n"
        )
    print(f"wrote          {target.relative_to(ROOT)}")

    if args.publish:
        published = publish(document, digest=digest, generated_at=now)
        print(f"published      {published.relative_to(ROOT)}")
        print(f"pointer        {POINTER.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
