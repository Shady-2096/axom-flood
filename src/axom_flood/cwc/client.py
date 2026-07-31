"""Client for the CWC Flood Forecasting System public JSON API.

The FFS site at https://ffs.india-water.gov.in is an Angular application that
reads these paths directly from the browser with no authentication. The contract
is not published as documentation, so every field this module depends on is
named explicitly here and validated in `pipeline.py` rather than trusted.

Two prefixes are in play, both served by the same host:

* ``/ffm/api/`` carries the operational warning list.
* ``/iam/api/`` carries the domain tables, queried with a JSON ``specification``
  filter DSL that the front end builds client-side.

Known server-side defect: ``new-forecasted-entry-data`` raises HTTP 500 with a
``JpaObjectRetrievalFailureException`` when the ``forecastedDate`` threshold
reaches back far enough to include forecasts whose aggregate row has been
deleted. The public site only ever queries forward from the current instant, so
`fetch_forecasts` does the same and treats the endpoint as best-effort.
"""

from __future__ import annotations

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx

logger = logging.getLogger(__name__)

# Observed failure modes from an otherwise healthy host: connect timeouts on
# individual endpoints and transient 5xx. Retried the way the ASDMA client does,
# because a single flaky read should not fail the daily run.
RETRY_STATUSES = frozenset({500, 502, 503, 504})

BASE_URL = "https://ffs.india-water.gov.in"
WARNING_PATH = "/ffm/api/station-water-level-above-warning/"
IST = ZoneInfo("Asia/Kolkata")

# Reduced water level in metres above mean sea level. This is the only datatype
# that may be compared against Warning, Danger and Highest Flood Level, because
# those thresholds are published on the same reduced-level datum.
#
# The same tables carry several other series for the same station and hour, and
# some of them look like plausible levels:
#
#   HZS  gauge height above the station's zero datum, not reduced level. At
#        Guwahati HHS is 48.04 while HZS is 8.06 against a danger level of
#        49.68, so storing HZS as a level would report a river forty metres
#        below danger while it sat just under it.
#   HZF  another gauge-height variant.
#   HHT  a second level series, offset from HHS by around a metre.
#   MPM  rainfall, reported on the half hour and usually 0.0.
#   MPS  rainfall, likewise.
#   BAT  sensor battery voltage.
#   FIN  reservoir inflow, not a river level at all.
#
# Filtering is therefore by datatype and never by whether a value looks
# reasonable: several of these are indistinguishable from a level by magnitude.
LEVEL_DATATYPE = "HHS"

# The station classes worth reading. FFS labels a forecast site `Level`, a
# reservoir site `Inflow`, and a plain observation site `Base`.
#
# `Base` was excluded until 2026-07-30, on the assumption that a station without
# a forecast carries no thresholds either. That is wrong: of the 70 Assam gauges
# ASDMA's own SMART AXOM dashboard publishes, 46 are `Base`, and 13 of those have
# a published danger level — Bhomoraguri on the Brahmaputra at Tezpur, Margherita
# on the Buridehing, Fulertal and Chotabekra on the Barak among them. Excluding
# the class dropped 43 live Assam gauges, most of the Barak valley among them.
#
# A `Base` station with no threshold is still worth carrying: it reports a level,
# which gives a trend, and the pipeline already handles a station whose alert
# status cannot be computed.
STATION_TYPES = ("Level", "Inflow", "Base")

USER_AGENT = "AxomFloodData/0.1"


def _eq(field: str, value: str) -> dict[str, Any]:
    return {
        "expression": {
            "valueIsRelationField": False,
            "fieldName": field,
            "operator": "eq",
            "value": value,
        }
    }


def _in(field: str, values: tuple[str, ...]) -> dict[str, Any]:
    """Match any of `values`.

    The specification DSL keys clauses as `where`/`and`/`or` in a single object,
    so three alternatives cannot be expressed as two `or` clauses. `in` takes the
    alternatives as one comma-joined string; a JSON list is rejected with 400.
    """
    return {
        "expression": {
            "valueIsRelationField": False,
            "fieldName": field,
            "operator": "in",
            "value": ",".join(values),
        }
    }


def _gt(field: str, value: str) -> dict[str, Any]:
    return {
        "expression": {
            "valueIsRelationField": False,
            "fieldName": field,
            "operator": "gt",
            "value": value,
        }
    }


def _ffs_naive(moment: datetime) -> str:
    """Render a timestamp the way the FFS front end does.

    The API compares against naive local timestamps and rejects a value without
    milliseconds with HTTP 500, so both details are reproduced deliberately.
    """
    local = moment.astimezone(IST).replace(tzinfo=None)
    return local.isoformat(timespec="milliseconds")


def parse_ffs_time(value: str) -> datetime:
    """Attach IST to an FFS timestamp, which is naive local time."""
    parsed = datetime.fromisoformat(value)
    return parsed.replace(tzinfo=IST) if parsed.tzinfo is None else parsed.astimezone(IST)


class FfsClient:
    """Thin, explicit wrapper over the FFS endpoints this project consumes."""

    def __init__(
        self,
        *,
        timeout: float = 120,
        base_url: str = BASE_URL,
        max_attempts: int = 3,
        retry_backoff_seconds: float = 2,
    ) -> None:
        self._base_url = base_url
        self._max_attempts = max(1, max_attempts)
        self._retry_backoff_seconds = retry_backoff_seconds
        self._client = httpx.Client(
            base_url=base_url,
            follow_redirects=True,
            timeout=timeout,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        )

    def __enter__(self) -> FfsClient:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def _get_json(self, path: str, params: dict[str, str] | None = None) -> Any:
        """GET with bounded retries for transport failures and transient 5xx.

        A malformed body is not retried: that is a contract problem, not a
        transient one, and it must surface rather than be papered over.
        """
        last_error: Exception | None = None
        for attempt in range(1, self._max_attempts + 1):
            try:
                response = self._client.get(path, params=params)
                response.raise_for_status()
                return response.json()
            except (httpx.TransportError, httpx.HTTPStatusError) as exc:
                if (
                    isinstance(exc, httpx.HTTPStatusError)
                    and exc.response.status_code not in RETRY_STATUSES
                ):
                    raise
                last_error = exc
                logger.warning(
                    "FFS GET %s attempt %d/%d failed: %s",
                    path,
                    attempt,
                    self._max_attempts,
                    type(exc).__name__,
                )
                if attempt < self._max_attempts:
                    time.sleep(self._retry_backoff_seconds * attempt)
        raise last_error if last_error else RuntimeError(f"FFS GET {path} failed")

    def _spec(self, resource: str, specification: dict[str, Any]) -> list[dict[str, Any]]:
        payload = self._get_json(
            f"/iam/api/{resource}/specification/",
            {"specification": json.dumps(specification, separators=(",", ":"))},
        )
        if not isinstance(payload, list):
            raise ValueError(f"FFS {resource} returned {type(payload).__name__}, expected a list")
        return payload

    def _all(self, resource: str) -> list[dict[str, Any]]:
        payload = self._get_json(f"/iam/api/{resource}/")
        if not isinstance(payload, list):
            raise ValueError(f"FFS {resource} returned {type(payload).__name__}, expected a list")
        return payload

    # -- slow-changing reference tables -----------------------------------

    def fetch_flood_forecast_static(self) -> list[dict[str, Any]]:
        """Warning level, danger level and highest flood level per station."""
        return self._spec(
            "flood-forecast-static",
            {"where": _in("type", STATION_TYPES)},
        )

    def fetch_layer_station(self) -> list[dict[str, Any]]:
        """Station identity, including the river id and the tahsil it sits in."""
        return self._spec(
            "layer-station",
            {"where": _in("floodForecastStaticStationCode.type", STATION_TYPES)},
        )

    def fetch_layer_station_geo(self) -> list[dict[str, Any]]:
        """Station name and coordinates. `layer-station` leaves lat/lon null."""
        return self._spec(
            "layer-station-geo",
            {
                "where": _in(
                    "layerStationStationCode.floodForecastStaticStationCode.type",
                    STATION_TYPES,
                )
            },
        )

    def fetch_rivers(self) -> list[dict[str, Any]]:
        return self._all("master-basin-localriver")

    def fetch_tahsils(self) -> list[dict[str, Any]]:
        return self._all("master-tahsil")

    def fetch_districts(self) -> list[dict[str, Any]]:
        return self._all("layer-district")

    def fetch_states(self) -> list[dict[str, Any]]:
        return self._all("layer-state")

    def fetch_reference(
        self, *, cache_dir: Path | None = None, cache_ttl_hours: float = 24
    ) -> dict[str, list[dict[str, Any]]]:
        """Fetch the reference tables, optionally reusing a recent local copy.

        These seven tables are about 15 MB and dominate run time: a full fetch has
        taken up to ~170 seconds, and every extra request is another chance for the
        host to time out. Their contents change on the order of months — the
        `savedAt` values are years old — so a bounded local reuse window trades
        nothing that matters for a large reduction in failure surface.

        Threshold values can legitimately change, which is why the window is
        bounded and short: at 24 hours a cached table is never more stale than the
        daily run cadence already implies.

        The cache is keyed by age alone, so widening `STATION_TYPES` would
        otherwise be invisible for a day: the run would reuse the narrower tables
        and report the old roster as if nothing had changed. A fingerprint of the
        requested station classes is stored alongside them and a mismatch discards
        the whole directory.
        """
        fetchers = {
            "flood_forecast_static": self.fetch_flood_forecast_static,
            "layer_station": self.fetch_layer_station,
            "layer_station_geo": self.fetch_layer_station_geo,
            "rivers": self.fetch_rivers,
            "tahsils": self.fetch_tahsils,
            "districts": self.fetch_districts,
            "states": self.fetch_states,
        }
        if cache_dir is None:
            return {name: fetch() for name, fetch in fetchers.items()}

        cache_dir.mkdir(parents=True, exist_ok=True)
        cutoff = time.time() - cache_ttl_hours * 3600

        fingerprint_path = cache_dir / "station-types.json"
        fingerprint = list(STATION_TYPES)
        try:
            reusable = json.loads(fingerprint_path.read_text()) == fingerprint
        except (OSError, json.JSONDecodeError):
            reusable = False
        if not reusable:
            logger.info("FFS reference cache built for other station classes; refetching")

        # Mismatched entries are ignored rather than deleted, and the fingerprint
        # is only written once every table has been refetched. FFS returns 500s
        # often enough that discarding the old tables up front would leave a
        # failed run with no cache at all.
        reference: dict[str, list[dict[str, Any]]] = {}
        for name, fetch in fetchers.items():
            path = cache_dir / f"{name}.json"
            if reusable and path.exists() and path.stat().st_mtime >= cutoff:
                try:
                    reference[name] = json.loads(path.read_text())
                    continue
                except (OSError, json.JSONDecodeError):
                    logger.warning("FFS reference cache for %s unreadable; refetching", name)
            rows = fetch()
            path.write_text(json.dumps(rows, ensure_ascii=False))
            reference[name] = rows
        fingerprint_path.write_text(json.dumps(fingerprint))
        return reference

    # -- per-run operational data -----------------------------------------

    def fetch_latest_levels(self) -> list[dict[str, Any]]:
        """Newest observed level per station, as `latestDataTime`/`latestDataValue`."""
        return self._spec(
            "new-entry-data-aggregate",
            {
                "where": _eq("id.datatypeCode", LEVEL_DATATYPE),
                "and": _in("stationCode.floodForecastStaticStationCode.type", STATION_TYPES),
            },
        )

    def fetch_above_warning(self) -> list[dict[str, Any]]:
        """CWC's own warning/danger classification and trend word per station."""
        payload = self._get_json(WARNING_PATH)
        if not isinstance(payload, list):
            raise ValueError("FFS above-warning returned a non-list payload")
        return payload

    def fetch_forecasts(self, *, now: datetime | None = None) -> list[dict[str, Any]]:
        """Approved forecasts issued for instants after `now`.

        Best-effort: see the module docstring on the endpoint's 500 defect.
        """
        threshold = _ffs_naive(now or datetime.now(IST))
        try:
            return self._spec(
                "new-forecasted-entry-data", _gt("id.forecastedDate", threshold)
            )
        except (httpx.HTTPStatusError, ValueError):
            return []

    def fetch_station_series(
        self, station_code: str, *, since: datetime
    ) -> list[dict[str, Any]]:
        """Reduced-level observations for one station after `since`.

        The response mixes every datatype the station reports at the same
        timestamps, so rows are restricted to `LEVEL_DATATYPE` here rather than
        downstream. Filtering happens in this process rather than in the query
        because the specification DSL's three-clause nesting is undocumented, and
        a filter that silently failed would admit gauge-height rows as levels.
        """
        rows = self._spec(
            "new-entry-data",
            {
                "where": _eq("id.stationCode", station_code),
                "and": _gt("id.dataTime", _ffs_naive(since)),
            },
        )
        return [row for row in rows if row.get("datatypeCode") == LEVEL_DATATYPE]

    def fetch_series_for(
        self,
        station_codes: list[str],
        *,
        since: datetime,
        max_workers: int = 4,
    ) -> dict[str, list[dict[str, Any]]]:
        """Backfill several stations concurrently.

        A bulk unfiltered query over `new-entry-data` exists but takes minutes,
        so per-station reads with bounded concurrency are used instead. Failures
        are per-station: a gauge that cannot be backfilled simply has no history
        and reports a null trend.
        """
        results: dict[str, list[dict[str, Any]]] = {}
        if not station_codes:
            return results

        def _one(code: str) -> tuple[str, list[dict[str, Any]]]:
            try:
                return code, self.fetch_station_series(code, since=since)
            except (httpx.HTTPError, ValueError):
                return code, []

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            for code, rows in pool.map(_one, station_codes):
                results[code] = rows
        return results
