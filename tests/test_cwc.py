"""Recorded-fixture tests for the CWC FFS gauge adapter.

Field names and value shapes are copied from live FFS responses observed on
2026-07-27, including the retired duplicate station codes that still serve 2022
readings and the naive-local timestamps the API returns.
"""

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from axom_flood.cwc.client import _ffs_naive, parse_ffs_time
from axom_flood.cwc.pipeline import gauge_id_for, ingest_cwc_gauges, load_district_lookup

IST = ZoneInfo("Asia/Kolkata")
NOW = datetime(2026, 7, 27, 15, 20, tzinfo=IST)

STATES = [
    {"stateCode": "18", "name": "Assam"},
    {"stateCode": "12", "name": "Arunachal Pradesh"},
    {"stateCode": "16", "name": "Tripura"},
]
DISTRICTS = [
    {"districtId": 201, "name": "DIBRUGARH", "stateCode": "18"},
    {"districtId": 202, "name": "GOLAGHAT", "stateCode": "18"},
    {"districtId": 203, "name": "CACHAR", "stateCode": "18"},
    {"districtId": 301, "name": "EAST SIANG", "stateCode": "12"},
    {"districtId": 401, "name": "Unakoti", "stateCode": "16"},
]
TAHSILS = [
    {"tahsilId": 1181071001, "name": "DIBRUGARH EAST", "districtId": 201},
    {"tahsilId": 1181091004, "name": "GOLAGHAT", "districtId": 202},
    {"tahsilId": 1181031002, "name": "SILCHAR", "districtId": 203},
    {"tahsilId": 1112011001, "name": "Pasighat", "districtId": 301},
    {"tahsilId": 1116011001, "name": "Unakoti", "districtId": 401},
]
RIVERS = [
    {"localriverId": 1251, "name": "Brahmaputra"},
    {"localriverId": 1310, "name": "Dhansiri (South)"},
    {"localriverId": 1400, "name": "Barak"},
    {"localriverId": 1500, "name": "Siang"},
    {"localriverId": 1600, "name": "Manu"},
]

# station_code, name, tahsil, river, WL, DL, HFL, lat, lon
_STATIONS = [
    ("010-UBDDIB", "Dibrugarh", 1181071001, 1251, 104.7, 105.7, 106.48, 27.4886, 94.9097),
    ("024-UBDDIB", "Numaligarh", 1181091004, 1310, 77.42, 78.42, 80.16, 26.6167, 93.7333),
    ("010-MBDGHY", "Annapurnaghat", 1181031002, 1400, 18.83, 19.83, 21.84, 24.8, 92.8),
    ("005-UBDDIB", "Passighat", 1112011001, 1500, 152.96, 153.96, 157.54, 28.0667, 95.3167),
    ("014-MDSIL", "KAILASHAHAR GDSQ SITE", 1116011001, 1600, 24.34, 25.34, 25.95, 24.33, 92.02),
]

FLOOD_FORECAST_STATIC = [
    {
        "stationCode": code,
        "type": "Level",
        "warningLevel": warning,
        "dangerLevel": danger,
        "highestFlowLevel": highest,
        "highestFlowLevelDate": "2024-07-01",
        "meteorologicalSubDivision": "Assam & Meghalaya",
    }
    for code, _name, _tahsil, _river, warning, danger, highest, _lat, _lon in _STATIONS
]
LAYER_STATION = [
    {
        "stationCode": code,
        "tahsilId": tahsil,
        "streamLocalriverId": river,
        "telemetric": True,
        "stationOperational": True,
        "lat": None,
        "lon": None,
    }
    for code, _name, tahsil, river, _w, _d, _h, _lat, _lon in _STATIONS
]
LAYER_STATION_GEO = [
    {"stationCode": code, "name": name, "lat": lat, "lon": lon, "type": "Level"}
    for code, name, _tahsil, _river, _w, _d, _h, lat, lon in _STATIONS
]

# An observation-only site. CWC publishes no forecast for it and no warning
# level, but it does publish a danger level, and it reports the same reduced
# level series as a forecast site. Bhomoraguri on the Brahmaputra at Tezpur is a
# real example of this shape.
BASE_STATION_CODE = "035"
FLOOD_FORECAST_STATIC.append(
    {
        "stationCode": BASE_STATION_CODE,
        "type": "Base",
        "warningLevel": None,
        "dangerLevel": 66.0,
        "highestFlowLevel": None,
        "highestFlowLevelDate": None,
        "meteorologicalSubDivision": "Assam & Meghalaya",
    }
)
LAYER_STATION.append(
    {
        "stationCode": BASE_STATION_CODE,
        "tahsilId": 1181091004,
        "streamLocalriverId": 1251,
        "telemetric": True,
        "stationOperational": True,
        "lat": None,
        "lon": None,
    }
)
LAYER_STATION_GEO.append(
    {
        "stationCode": BASE_STATION_CODE,
        "name": "Bhomoraguri",
        "lat": 26.6103,
        "lon": 92.8603,
        "type": "Base",
    }
)

def _latest(code: str, data_time: str, value: float) -> dict:
    return {"stationCode": code, "latestDataTime": data_time, "latestDataValue": value}


LATEST_LEVELS = [
    # Between warning and danger level.
    _latest("010-UBDDIB", "2026-07-27T14:00:00", 104.82),
    # Above danger level.
    _latest("024-UBDDIB", "2026-07-27T14:00:00", 78.75),
    # Retired duplicate code that still serves a 2022 reading.
    _latest("010-MBDGHY", "2022-10-12T09:00:00", 14.67),
    _latest("005-UBDDIB", "2026-07-27T12:00:00", 150.16),
    # Below its danger level of 66.0.
    _latest("035", "2026-07-27T14:00:00", 64.3),
    _latest("014-MDSIL", "2026-07-27T12:00:00", 18.85),
]
ABOVE_WARNING = [
    {"stationCode": "010-UBDDIB", "status": "WARNING", "trend": "STEADY", "value": 104.82},
    {"stationCode": "024-UBDDIB", "status": "DANGER", "trend": "FALLING", "value": 78.75},
]
FORECASTS = [
    {
        "stationCode": "024-UBDDIB",
        "datatypeCode": "HHS",
        "pendingOfApproval": False,
        "realValue": 78.63,
        "revised": False,
        "trend": "Falling",
        "id": {
            "stationCode": "024-UBDDIB",
            "datatypeCode": "HHS",
            "forecastNo": 11,
            "forecastedDate": "2026-07-27T21:00:00",
            "issuedDate": "2026-07-27T09:04:00",
        },
    },
    {
        "stationCode": "024-UBDDIB",
        "datatypeCode": "HHS",
        "pendingOfApproval": False,
        "realValue": 78.10,
        "revised": False,
        "trend": "Falling",
        "id": {
            "stationCode": "024-UBDDIB",
            "datatypeCode": "HHS",
            "forecastNo": 12,
            "forecastedDate": "2026-07-28T09:00:00",
            "issuedDate": "2026-07-27T09:04:00",
        },
    },
    # Inflow forecasts are not river-gauge levels and must be ignored.
    {
        "stationCode": "010-UBDDIB",
        "datatypeCode": "FIN",
        "pendingOfApproval": False,
        "realValue": 1750.0,
        "id": {
            "stationCode": "010-UBDDIB",
            "datatypeCode": "FIN",
            "forecastNo": 13,
            "forecastedDate": "2026-07-28T08:00:00",
            "issuedDate": "2026-07-27T09:20:00",
        },
    },
]



def _hhs(data_time: str, value: float) -> dict:
    """A reduced-level series row, shaped the way the live API returns them."""
    return {
        "id": {"dataTime": data_time, "datatypeCode": "HHS", "stationCode": "x"},
        "datatypeCode": "HHS",
        "dataValue": value,
    }

class FakeFfsClient:
    """Serves the recorded fixtures without touching the network."""

    def __init__(
        self,
        series: dict[str, list[dict]] | None = None,
        above_warning: list[dict] | None = None,
        latest_levels: list[dict] | None = None,
    ) -> None:
        self._series = series or {}
        self._above_warning = ABOVE_WARNING if above_warning is None else above_warning
        self._latest_levels = LATEST_LEVELS if latest_levels is None else latest_levels
        self.series_requested_for: list[str] = []

    def fetch_reference(self, *, cache_dir=None, cache_ttl_hours=24) -> dict[str, list[dict]]:
        return {
            "flood_forecast_static": FLOOD_FORECAST_STATIC,
            "layer_station": LAYER_STATION,
            "layer_station_geo": LAYER_STATION_GEO,
            "rivers": RIVERS,
            "tahsils": TAHSILS,
            "districts": DISTRICTS,
            "states": STATES,
        }

    def fetch_latest_levels(self) -> list[dict]:
        return self._latest_levels

    def fetch_above_warning(self) -> list[dict]:
        return self._above_warning

    def fetch_forecasts(self, *, now=None) -> list[dict]:
        return FORECASTS

    def fetch_series_for(self, station_codes, *, since, max_workers=4) -> dict[str, list[dict]]:
        self.series_requested_for = list(station_codes)
        return {code: self._series.get(code, []) for code in station_codes}

    def close(self) -> None:  # pragma: no cover - the pipeline must not close a passed client
        raise AssertionError("pipeline closed a client it does not own")


def _run(tmp_path: Path, **kwargs) -> dict:
    client = kwargs.pop("client", None) or FakeFfsClient()
    result = ingest_cwc_gauges(data_dir=tmp_path, now=NOW, client=client, **kwargs)
    return json.loads(Path(result["json"]).read_text())


def _by_code(document: dict) -> dict[str, dict]:
    return {station["cwc_station_code"]: station for station in document["stations"]}


def test_only_assam_and_configured_upstream_states_are_selected(tmp_path: Path) -> None:
    stations = _by_code(_run(tmp_path))
    assert "014-MDSIL" not in stations, "a Tripura gauge must not enter an Assam feed"
    assert stations["005-UBDDIB"]["is_upstream_of_assam"] is True
    assert stations["010-UBDDIB"]["is_upstream_of_assam"] is False


def test_observation_only_base_stations_are_carried(tmp_path: Path) -> None:
    """Excluding `Base` dropped 43 live Assam gauges, most of the Barak valley."""
    station = _by_code(_run(tmp_path))[BASE_STATION_CODE]
    assert station["station_type"] == "Base"
    assert station["level_m"] == 64.3
    assert station["danger_level_m"] == 66.0
    assert station["warning_level_m"] is None


def test_a_base_station_without_a_warning_level_still_raises_danger(tmp_path: Path) -> None:
    client = FakeFfsClient(latest_levels=[_latest(BASE_STATION_CODE, "2026-07-27T14:00:00", 66.4)])
    document = _run(tmp_path, client=client)
    assert _by_code(document)[BASE_STATION_CODE]["status"] == "above_danger"
    assert document["stations_at_or_above_danger"] == [
        _by_code(document)[BASE_STATION_CODE]["gauge_id"]
    ]


def test_revenue_circle_comes_from_the_asdma_crosswalk(tmp_path: Path) -> None:
    """FFS resolves only to a tahsil, so the circle can only come from ASDMA."""
    crosswalk = tmp_path / "circles.json"
    crosswalk.write_text(
        json.dumps(
            {
                "stations": [
                    {"cwc_station_code": "010-UBDDIB", "revenue_circle_source_name": "Silchar"},
                    # Disambiguated by district, as SMART AXOM writes it.
                    {
                        "cwc_station_code": "024-UBDDIB",
                        "revenue_circle_source_name": "Nazira_sivasagar",
                    },
                    # Not a circle at all; must stay unresolved rather than guess.
                    {
                        "cwc_station_code": "005-UBDDIB",
                        "revenue_circle_source_name": "River_brahmaputra",
                    },
                ]
            }
        )
    )
    stations = _by_code(_run(tmp_path, circle_crosswalk=crosswalk))
    assert stations["010-UBDDIB"]["revenue_circle"] == "Silchar"
    assert stations["024-UBDDIB"]["revenue_circle"] == "Nazira"
    assert stations["024-UBDDIB"]["revenue_circle_source_name"] == "Nazira_sivasagar"
    assert stations["005-UBDDIB"]["revenue_circle"] is None
    assert stations["005-UBDDIB"]["revenue_circle_source_name"] == "River_brahmaputra"


def test_a_missing_crosswalk_costs_the_circle_not_the_reading(tmp_path: Path) -> None:
    stations = _by_code(_run(tmp_path, circle_crosswalk=tmp_path / "absent.json"))
    assert stations["010-UBDDIB"]["revenue_circle"] is None
    assert stations["010-UBDDIB"]["level_m"] == 104.82


def test_district_and_river_come_from_the_agency_tables(tmp_path: Path) -> None:
    station = _by_code(_run(tmp_path))["010-UBDDIB"]
    assert station["district"] == "Dibrugarh"
    assert station["district_slug"] == "dibrugarh"
    assert station["state"] == "Assam"
    assert station["river"] == "Brahmaputra"
    assert station["site_name"] == "Dibrugarh"
    assert station["coordinates"] == [94.9097, 27.4886]


def test_cwc_district_spellings_resolve_to_the_canonical_registry(tmp_path: Path) -> None:
    lookup = load_district_lookup(Path("config/assam-districts.json"))
    # The three spellings CWC uses that the registry has to reconcile.
    assert lookup["marigaon"] == ("Morigaon", "morigaon")
    assert lookup["sivsagar"] == ("Sivasagar", "sivasagar")
    assert lookup["karimganj"] == ("Sribhumi", "sribhumi")
    assert lookup["dibrugarh"] == ("Dibrugarh", "dibrugarh")


def test_unknown_district_spelling_is_reported_not_silently_mapped(tmp_path: Path) -> None:
    registry = tmp_path / "districts.json"
    registry.write_text(json.dumps({"districts": [{"name": "Golaghat", "slug": "golaghat"}]}))
    document = ingest_cwc_gauges(
        data_dir=tmp_path,
        now=NOW,
        client=FakeFfsClient(),
        district_registry=registry,
    )
    stations = _by_code(json.loads(Path(document["json"]).read_text()))
    # Golaghat is known, so it resolves.
    assert stations["024-UBDDIB"]["district_slug"] == "golaghat"
    # Dibrugarh is not in this cut-down registry: kept, flagged, never guessed.
    assert stations["010-UBDDIB"]["district"] == "Dibrugarh"
    assert stations["010-UBDDIB"]["district_slug"] is None
    assert "DIBRUGARH" in document["unmapped_district_names"]


def test_thresholds_drive_status(tmp_path: Path) -> None:
    stations = _by_code(_run(tmp_path))
    assert stations["010-UBDDIB"]["status"] == "warning"
    assert stations["024-UBDDIB"]["status"] == "above_danger"
    assert stations["024-UBDDIB"]["danger_level_m"] == 78.42
    assert stations["024-UBDDIB"]["highest_flood_level_m"] == 80.16


def test_retired_duplicate_station_reports_no_data_and_withholds_level(tmp_path: Path) -> None:
    station = _by_code(_run(tmp_path))["010-MBDGHY"]
    assert station["status"] == "no_data"
    assert station["level_m"] is None
    assert station["last_observed_level_m"] == 14.67
    assert station["data_age_hours"] > 6
    # CWC's own classification must not be presented for a stale gauge either.
    assert station["cwc_status"] is None
    assert station["cwc_trend"] is None


def test_stale_stations_are_excluded_from_alert_rollups(tmp_path: Path) -> None:
    document = _run(tmp_path)
    stale_id = gauge_id_for("010-MBDGHY", "Annapurnaghat")
    assert stale_id not in document["stations_at_or_above_warning"]
    assert document["stations_with_no_data"] == 1
    assert document["stations_at_or_above_danger"] == [gauge_id_for("024-UBDDIB", "Numaligarh")]


def test_cwc_classification_is_reported_present_when_it_is(tmp_path: Path) -> None:
    stations = _by_code(_run(tmp_path))
    assert stations["024-UBDDIB"]["cwc_status"] == "DANGER"
    assert stations["024-UBDDIB"]["cwc_trend"] == "FALLING"
    assert stations["024-UBDDIB"]["cwc_classification_available"] is True


def test_empty_cwc_warning_list_is_not_treated_as_an_all_clear(tmp_path: Path) -> None:
    """An empty national warning list has been served transiently by a healthy host.

    Reading it as "nothing is above warning" would suppress a real danger-level
    alert, so it must degrade context only.
    """
    client = FakeFfsClient(above_warning=[])
    result = ingest_cwc_gauges(data_dir=tmp_path, now=NOW, client=client)
    document = json.loads(Path(result["json"]).read_text())
    stations = _by_code(document)

    assert document["cwc_classification_available"] is False
    assert document["source_warnings"], "an unavailable warning list must be disclosed"
    assert stations["024-UBDDIB"]["cwc_classification_available"] is False
    assert stations["024-UBDDIB"]["cwc_status"] is None
    # The alert itself is derived from the level against the published threshold,
    # so it survives the outage.
    assert stations["024-UBDDIB"]["status"] == "above_danger"
    assert result["stations_at_or_above_danger"] == [gauge_id_for("024-UBDDIB", "Numaligarh")]


def test_nearest_approved_level_forecast_is_attached(tmp_path: Path) -> None:
    stations = _by_code(_run(tmp_path))
    forecast = stations["024-UBDDIB"]["forecast"]
    assert forecast["forecast_level_m"] == 78.63
    assert forecast["forecast_for"] == "2026-07-27T21:00:00+05:30"
    assert forecast["issued_at"] == "2026-07-27T09:04:00+05:30"
    assert forecast["trend_word"] == "Falling"
    # An inflow forecast is not a river level.
    assert stations["010-UBDDIB"]["forecast"] is None


def test_duplicate_site_names_get_distinct_gauge_ids() -> None:
    assert gauge_id_for("010-MBDGHY", "Annapurnaghat") != gauge_id_for(
        "01-11-01-007", "Annapurnaghat"
    )


def test_trend_is_published_only_from_a_continuous_backfilled_window(tmp_path: Path) -> None:
    series = {
        "010-UBDDIB": [
            _hhs(f"2026-07-27T{hour:02d}:00:00", 104.7 + hour * 0.01)
            for hour in range(11, 15)
        ]
    }
    stations = _by_code(_run(tmp_path, client=FakeFfsClient(series), backfill_hours=12))
    station = stations["010-UBDDIB"]
    assert station["readings_in_local_series"] == 4
    assert station["trend_cm_per_hr"] == 1.0
    assert station["gap_detected_in_trend_window"] is False
    # No backfill for a station means no history and therefore no trend.
    assert stations["024-UBDDIB"]["trend_cm_per_hr"] is None


def test_readings_accumulate_without_duplicates_across_runs(tmp_path: Path) -> None:
    first = ingest_cwc_gauges(data_dir=tmp_path, now=NOW, client=FakeFfsClient())
    second = ingest_cwc_gauges(data_dir=tmp_path, now=NOW, client=FakeFfsClient())
    # Every fixture reading but the Tripura one, which is outside the roster.
    assert first["readings_added"] == 5
    assert second["readings_added"] == 0


def test_station_dropping_out_of_the_feed_becomes_no_data_not_absent(tmp_path: Path) -> None:
    """Telemetry failure during a flood looks exactly like a station disappearing.

    It must degrade to `no_data` against its last known reading rather than
    silently leaving the feed, which would read as "this gauge is fine".
    """
    # First run: the station reports normally and history is stored.
    first = ingest_cwc_gauges(data_dir=tmp_path, now=NOW, client=FakeFfsClient())
    assert "024-UBDDIB" in _by_code(json.loads(Path(first["json"]).read_text()))

    # Second run, 9 hours later: CWC stops returning that station entirely.
    dropped = [row for row in LATEST_LEVELS if row["stationCode"] != "024-UBDDIB"]
    later = NOW.replace(hour=23, minute=30)
    second = ingest_cwc_gauges(
        data_dir=tmp_path, now=later, client=FakeFfsClient(latest_levels=dropped)
    )
    document = json.loads(Path(second["json"]).read_text())
    station = _by_code(document)["024-UBDDIB"]

    assert station["status"] == "no_data"
    assert station["level_m"] is None
    assert station["last_observed_level_m"] == 78.75
    assert station["in_latest_source_response"] is False
    assert station["data_age_hours"] > 6
    assert "024-UBDDIB" in document["stations_missing_from_latest_response"]
    # It is not counted as a station that never reported.
    assert "024-UBDDIB" not in document["stations_without_any_reading"]
    # And it must not be presented as an active danger alert on stale data.
    assert station["gauge_id"] not in document["stations_at_or_above_danger"]


def test_a_station_that_never_reported_is_not_invented(tmp_path: Path) -> None:
    dropped = [row for row in LATEST_LEVELS if row["stationCode"] != "024-UBDDIB"]
    result = ingest_cwc_gauges(
        data_dir=tmp_path, now=NOW, client=FakeFfsClient(latest_levels=dropped)
    )
    document = json.loads(Path(result["json"]).read_text())
    assert "024-UBDDIB" not in _by_code(document)
    assert "024-UBDDIB" in document["stations_without_any_reading"]


def test_every_published_reading_is_inside_the_revision_it_cites(tmp_path: Path) -> None:
    """A stored reading must be recoverable from the raw body it names."""
    series = {
        "010-UBDDIB": [
            _hhs(f"2026-07-27T{hour:02d}:00:00", 104.7 + hour * 0.01)
            for hour in range(11, 15)
        ]
    }
    result = ingest_cwc_gauges(
        data_dir=tmp_path, now=NOW, client=FakeFfsClient(series), backfill_hours=12
    )
    raw = json.loads(Path(result["raw"]).read_text())
    stored = (tmp_path / "series" / "gauges" / "cwc_dibrugarh_010_ubddib.jsonl").read_text()
    rows = [json.loads(line) for line in stored.splitlines() if line]

    # The backfilled observations are present in the cited raw body.
    raw_times = {entry["id"]["dataTime"] for entry in raw["series"]["010-UBDDIB"]}
    assert raw_times == {f"2026-07-27T{hour:02d}:00:00" for hour in range(11, 15)}
    # The aggregate's own newest reading is in the same body.
    assert any(entry["stationCode"] == "010-UBDDIB" for entry in raw["latest_levels"])
    # Every stored observation resolves to a timestamp the cited body contains.
    citable = raw_times | {
        entry["latestDataTime"]
        for entry in raw["latest_levels"]
        if entry["stationCode"] == "010-UBDDIB"
    }
    for row in rows:
        assert row["source_revision"] == Path(result["raw"]).stem
        assert row["observed_at"][:19] in citable

    # Thresholds and labels are preserved under their own revision.
    document = json.loads(Path(result["json"]).read_text())
    reference = json.loads(Path(result["reference"]).read_text())
    assert document["reference_revision"] == Path(result["reference"]).stem
    assert reference["stations"]["010-UBDDIB"]["danger_level_m"] == 105.7
    assert _by_code(document)["010-UBDDIB"]["reference_revision"] == document["reference_revision"]


def test_reference_cache_avoids_refetching_within_the_window(tmp_path: Path) -> None:
    import httpx

    from axom_flood.cwc.client import FfsClient

    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(200, json=[{"stationCode": "010-UBDDIB"}])

    def build() -> FfsClient:
        client = FfsClient(retry_backoff_seconds=0)
        client._client = httpx.Client(
            base_url="https://ffs.test", transport=httpx.MockTransport(handler)
        )
        return client

    cache = tmp_path / "cache"
    build().fetch_reference(cache_dir=cache)
    first = len(calls)
    assert first == 7, "all seven reference tables fetched on a cold cache"

    build().fetch_reference(cache_dir=cache)
    assert len(calls) == first, "a warm cache must not refetch"

    # Expired cache refetches rather than serving something arbitrarily old.
    build().fetch_reference(cache_dir=cache, cache_ttl_hours=0)
    assert len(calls) == first * 2


def test_widening_the_station_classes_invalidates_the_reference_cache(tmp_path: Path) -> None:
    """A cache keyed by age alone would hide a roster change for a whole day."""
    import httpx

    from axom_flood.cwc import client as client_module
    from axom_flood.cwc.client import FfsClient

    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(200, json=[{"stationCode": "010-UBDDIB"}])

    def build() -> FfsClient:
        client = FfsClient(retry_backoff_seconds=0)
        client._client = httpx.Client(
            base_url="https://ffs.test", transport=httpx.MockTransport(handler)
        )
        return client

    cache = tmp_path / "cache"
    build().fetch_reference(cache_dir=cache)
    first = len(calls)
    build().fetch_reference(cache_dir=cache)
    assert len(calls) == first, "a warm cache must not refetch"

    original = client_module.STATION_TYPES
    client_module.STATION_TYPES = (*original, "Reservoir")
    try:
        build().fetch_reference(cache_dir=cache)
    finally:
        client_module.STATION_TYPES = original
    assert len(calls) == first * 2, "a cache built for other station classes must be discarded"


def test_only_the_reduced_level_datatype_enters_the_level_history() -> None:
    """Gauge height shares a station and hour with the level but not its datum.

    At Guwahati HZS reads 8.06 where HHS is 48.04 against a danger level of 49.68,
    so admitting HZS would report a river forty metres below danger while it sat
    just under it. HZS is deliberately listed first here: correctness must not
    depend on which datatype the response happens to return first.
    """
    import httpx

    from axom_flood.cwc.client import FfsClient

    rows = [
        {"id": {"dataTime": "2026-07-27T14:00:00", "datatypeCode": "HZS"},
         "datatypeCode": "HZS", "dataValue": 8.06, "stationCode": "001-MBDGHY"},
        {"id": {"dataTime": "2026-07-27T14:00:00", "datatypeCode": "HHT"},
         "datatypeCode": "HHT", "dataValue": 49.9, "stationCode": "001-MBDGHY"},
        {"id": {"dataTime": "2026-07-27T14:00:00", "datatypeCode": "BAT"},
         "datatypeCode": "BAT", "dataValue": 12.9, "stationCode": "001-MBDGHY"},
        {"id": {"dataTime": "2026-07-27T14:30:00", "datatypeCode": "MPS"},
         "datatypeCode": "MPS", "dataValue": 0.0, "stationCode": "001-MBDGHY"},
        {"id": {"dataTime": "2026-07-27T14:00:00", "datatypeCode": "HHS"},
         "datatypeCode": "HHS", "dataValue": 48.04, "stationCode": "001-MBDGHY"},
    ]
    client = FfsClient(retry_backoff_seconds=0)
    client._client = httpx.Client(
        base_url="https://ffs.test",
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=rows)),
    )
    kept = client.fetch_station_series("001-MBDGHY", since=NOW)
    assert [row["dataValue"] for row in kept] == [48.04]


def test_gauge_height_never_reaches_a_published_level(tmp_path: Path) -> None:
    """End to end: a gauge-height row offered before the level must not win."""
    series = {
        "010-UBDDIB": [
            # Ordered adversarially, and both would pass the shape check.
            {"id": {"dataTime": "2026-07-27T14:00:00"}, "datatypeCode": "HZS",
             "dataValue": 12.4},
            {"id": {"dataTime": "2026-07-27T14:00:00"}, "datatypeCode": "HHS",
             "dataValue": 104.82},
        ]
    }
    station = _by_code(
        _run(tmp_path, client=FakeFfsClient(series), backfill_hours=12)
    )["010-UBDDIB"]
    assert station["last_observed_level_m"] == 104.82
    stored = (tmp_path / "series" / "gauges" / f"{station['gauge_id']}.jsonl").read_text()
    levels = [json.loads(line)["level_m"] for line in stored.splitlines() if line]
    assert 12.4 not in levels


def test_half_hour_placeholder_rows_are_rejected() -> None:
    from axom_flood.cwc.pipeline import is_plausible_level

    on_hour = datetime(2026, 7, 27, 14, 0, tzinfo=IST)
    half_hour = datetime(2026, 7, 27, 14, 30, tzinfo=IST)
    assert is_plausible_level(on_hour, 78.75) is True
    # Exactly 0.0 is the common placeholder; 0.6 where the level is ~15 m is the
    # partially-garbage variant. Both arrive on the half hour.
    assert is_plausible_level(half_hour, 0.0) is False
    assert is_plausible_level(half_hour, 0.6) is False
    assert is_plausible_level(half_hour, 78.75) is False
    assert is_plausible_level(on_hour, 0.0) is False
    # A high or fast-moving reading is never filtered: that is the flood signal.
    assert is_plausible_level(on_hour, 999.0) is True


def test_placeholder_row_never_becomes_the_published_level(tmp_path: Path) -> None:
    """The worst failure mode: a 0.0 as the newest reading would report `normal`."""
    series = {
        "024-UBDDIB": [
            _hhs("2026-07-27T13:00:00", 78.70),
            _hhs("2026-07-27T14:00:00", 78.75),
            # Newer than every real reading, and pure placeholder.
            _hhs("2026-07-27T14:30:00", 0.0),
        ]
    }
    result = ingest_cwc_gauges(
        data_dir=tmp_path, now=NOW, client=FakeFfsClient(series), backfill_hours=12
    )
    station = _by_code(json.loads(Path(result["json"]).read_text()))["024-UBDDIB"]
    assert station["level_m"] == 78.75
    assert station["observed_at"] == "2026-07-27T14:00:00+05:30"
    assert station["status"] == "above_danger"
    assert result["readings_rejected_implausible"] >= 1

    stored = (tmp_path / "series" / "gauges" / station["gauge_id"]).with_suffix(".jsonl")
    levels = [json.loads(line)["level_m"] for line in stored.read_text().splitlines() if line]
    assert 0.0 not in levels, "a placeholder must never reach the append-only series"


def test_placeholder_rows_cannot_distort_a_trend(tmp_path: Path) -> None:
    series = {
        "010-UBDDIB": [
            _hhs(f"2026-07-27T{hour:02d}:00:00", 104.7 + hour * 0.01)
            for hour in range(11, 15)
        ]
        + [_hhs("2026-07-27T12:30:00", 0.0)]
    }
    station = _by_code(
        _run(tmp_path, client=FakeFfsClient(series), backfill_hours=12)
    )["010-UBDDIB"]
    assert station["readings_in_local_series"] == 4
    # Same trend as the clean series: the placeholder had no effect.
    assert station["trend_cm_per_hr"] == 1.0


def test_transient_failures_are_retried_but_contract_errors_are_not() -> None:
    import httpx

    from axom_flood.cwc.client import FfsClient

    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        # Fail twice the way the live host does, then succeed.
        if len(calls) < 3:
            return httpx.Response(503)
        return httpx.Response(200, json=[{"stationCode": "010-UBDDIB"}])

    client = FfsClient(retry_backoff_seconds=0)
    client._client = httpx.Client(
        base_url="https://ffs.test", transport=httpx.MockTransport(handler)
    )
    assert client.fetch_above_warning() == [{"stationCode": "010-UBDDIB"}]
    assert len(calls) == 3

    # A 404 is a contract problem and must surface immediately.
    not_found = FfsClient(retry_backoff_seconds=0)
    attempts: list[int] = []

    def missing(request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        return httpx.Response(404)

    not_found._client = httpx.Client(
        base_url="https://ffs.test", transport=httpx.MockTransport(missing)
    )
    with pytest.raises(httpx.HTTPStatusError):
        not_found.fetch_above_warning()
    assert len(attempts) == 1


def test_ffs_timestamps_carry_milliseconds_and_ist() -> None:
    # The specification endpoint answers HTTP 500 without the millisecond field.
    rendered = _ffs_naive(datetime(2026, 7, 27, 9, 48, 56, 990000, tzinfo=ZoneInfo("UTC")))
    assert rendered == "2026-07-27T15:18:56.990"
    assert parse_ffs_time("2026-07-27T15:00:00").utcoffset().total_seconds() == 5.5 * 3600


@pytest.mark.parametrize(
    ("level", "expected"),
    [(104.0, "normal"), (104.7, "warning"), (105.7, "above_danger"), (106.48, "above_hfl")],
)
def test_status_boundaries_are_inclusive(level: float, expected: str, tmp_path: Path) -> None:
    from axom_flood.cwc.pipeline import _level_status

    assert _level_status(level, warning=104.7, danger=105.7, highest=106.48) == expected
