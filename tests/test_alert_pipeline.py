import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from axom_flood.alerts.pipeline import run_alerts

IST = ZoneInfo("Asia/Kolkata")


def _station(level: float) -> dict:
    return {
        "gauge_id": "cwc_sivasagar_018_ubddib",
        "cwc_station_code": "018-ubddib",
        "river": "Dikhow",
        "site_name": "Sivasagar",
        "status": "above_danger",
        "level_m": level,
        "warning_level_m": 86.2,
        "danger_level_m": 87.2,
        "highest_flood_level_m": 89.1,
        "highest_flood_level_date": "2019-07-15",
        "trend_cm_per_hr": 10,
        "forecast": None,
        "source_url": "https://example.invalid/cwc",
    }


def _localities(path: Path) -> Path:
    path.write_text(
        json.dumps(
            {
                "localities": [
                    {
                        "locality_id": "sivasagar-nazira",
                        "revenue_circle": "Nazira",
                        "primary_gauge": "018-ubddib",
                    }
                ]
            }
        )
    )
    return path


def test_pipeline_joins_circle_to_station_code_and_emits_immutable_artifacts(
    tmp_path: Path,
) -> None:
    localities = tmp_path / "localities.json"
    localities.write_text(
        json.dumps(
            {
                "localities": [
                    {
                        "locality_id": "sivasagar-nazira",
                        "revenue_circle": "Nazira",
                        "primary_gauge": "018-ubddib",
                    }
                ]
            }
        )
    )
    cwc = tmp_path / "cwc.json"
    cwc.write_text(
        json.dumps(
            {
                "stations": [
                    {
                        "gauge_id": "cwc_sivasagar_018_ubddib",
                        "cwc_station_code": "018-ubddib",
                        "river": "Dikhow",
                        "site_name": "Sivasagar",
                        "status": "above_danger",
                        "level_m": 87.3,
                        "warning_level_m": 86.2,
                        "danger_level_m": 87.2,
                        "highest_flood_level_m": 89.1,
                        "highest_flood_level_date": "2019-07-15",
                        "trend_cm_per_hr": 10,
                        "forecast": None,
                        "source_url": "https://example.invalid/cwc",
                    }
                ]
            }
        )
    )
    series = tmp_path / "series" / "gauges" / "cwc_sivasagar_018_ubddib.jsonl"
    series.parent.mkdir(parents=True)
    series.write_text(
        "\n".join(
            json.dumps({"observed_at": f"2026-07-27T{hour}:00:00+05:30", "level_m": level})
            for hour, level in [("19", 87.1), ("20", 87.3)]
        )
        + "\n"
    )
    result = run_alerts(
        data_dir=tmp_path,
        localities_path=localities,
        cwc_snapshot=cwc,
        now=datetime(2026, 7, 27, 20, 0, tzinfo=IST),
    )
    assert result["alerts_emitted"] == 1
    assert result["pushes_ready"] == 1
    assert all(Path(path).exists() for path in result["alerts"][0]["artifacts"].values())
    assert len((tmp_path / "series" / "alerts.jsonl").read_text().splitlines()) == 1


def _snapshot_dir(data_dir: Path, wanted: str, others: list[str]) -> Path:
    """A CWC directory holding several snapshots and a pointer naming `wanted`."""

    directory = data_dir / "processed" / "cwc"
    directory.mkdir(parents=True)
    for name, level in [(wanted, 87.3), *[(name, 80.0) for name in others]]:
        (directory / f"{name}.json").write_text(json.dumps({"stations": [_station(level)]}))
    (directory / "current.json").write_text(
        json.dumps({"record": "cwc_snapshot_pointer", "revision_id": wanted})
    )
    series = data_dir / "series" / "gauges" / "cwc_sivasagar_018_ubddib.jsonl"
    series.parent.mkdir(parents=True)
    series.write_text(
        "\n".join(
            json.dumps({"observed_at": f"2026-07-27T{hour}:00:00+05:30", "level_m": level})
            for hour, level in [("19", 87.1), ("20", 87.3)]
        )
        + "\n"
    )
    return directory


def test_the_default_snapshot_comes_from_the_pointer_not_the_newest_file(
    tmp_path: Path,
) -> None:
    """Without an explicit `--cwc-snapshot`, the pointer decides.

    Two separate failures lived here, and neither showed in the output.

    `current.json` is in the same directory and the ingest writes it *after* the
    snapshot it names, so under a newest-modification-time rule the pointer was
    usually the newest file -- and it has no `stations`, so the whole run died on
    a KeyError. When it did not win, a fresh `git clone` had stamped all 213
    snapshots with one checkout time and the pick was whichever hash the
    filesystem returned first: alerts evaluated against a ten-day-old river.
    """

    directory = _snapshot_dir(tmp_path, "wanted", ["stale-a", "stale-b"])
    # The failing arrangement exactly: pointer newest, a stale snapshot after it.
    os.utime(directory / "current.json", (2_000_000_000, 2_000_000_000))
    os.utime(directory / "stale-a.json", (1_900_000_000, 1_900_000_000))

    result = run_alerts(
        data_dir=tmp_path,
        localities_path=_localities(tmp_path / "localities.json"),
        now=datetime(2026, 7, 27, 20, 0, tzinfo=IST),
    )

    assert Path(result["cwc_snapshot"]).name == "wanted.json"
    assert result["alerts_emitted"] == 1


def test_a_missing_pointer_is_fatal_rather_than_a_guess(tmp_path: Path) -> None:
    """A directory full of snapshots and no pointer has no right answer in it."""

    directory = tmp_path / "processed" / "cwc"
    directory.mkdir(parents=True)
    (directory / "orphan.json").write_text(json.dumps({"stations": [_station(87.3)]}))

    with pytest.raises(RuntimeError, match="current.json"):
        run_alerts(
            data_dir=tmp_path,
            localities_path=_localities(tmp_path / "localities.json"),
            now=datetime(2026, 7, 27, 20, 0, tzinfo=IST),
        )
