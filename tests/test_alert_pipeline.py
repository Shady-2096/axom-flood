import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from axom_flood.alerts.pipeline import run_alerts

IST = ZoneInfo("Asia/Kolkata")


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
