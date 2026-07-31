from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import Image

from axom_flood.alerts.engine import evaluate_alert, persist_alert_artifacts

IST = ZoneInfo("Asia/Kolkata")
NOW = datetime(2026, 7, 27, 20, 0, tzinfo=IST)
LOCALITY = {
    "locality_id": "sivasagar-nazira",
    "revenue_circle": "Nazira",
}


def gauge(**overrides):
    value = {
        "gauge_id": "cwc_sivasagar_018_ubddib",
        "river": "Dikhow",
        "site_name": "Sivasagar",
        "status": "above_danger",
        "level_m": 87.3,
        "warning_level_m": 86.2,
        "danger_level_m": 87.2,
        "highest_flood_level_m": 89.1,
        "highest_flood_level_date": "2019-07-15",
        "trend_cm_per_hr": 10.0,
        "forecast": None,
        "reference_floods": [],
        "source_url": "https://ffs.india-water.gov.in/#/station/018-ubddib",
        "data_age_hours": 0.5,
        "cwc_status": "NORMAL",
    }
    value.update(overrides)
    return value


def reading(level):
    return {"level_m": level}


def test_threshold_crossing_drives_watch_not_cwc_convenience_status() -> None:
    alert = evaluate_alert(
        LOCALITY,
        gauge(cwc_status="NORMAL"),
        [reading(87.1), reading(87.3)],
        now=NOW,
        active_event=False,
    )
    assert alert["severity"] == "watch"
    assert alert["push"] is True


def test_hfl_projection_is_severe_and_official_forecast_is_preferred() -> None:
    alert = evaluate_alert(
        LOCALITY,
        gauge(
            forecast={
                "forecast_level_m": 89.2,
                "forecast_for": "2026-07-28T08:00:00+05:30",
            }
        ),
        [reading(87.2), reading(87.3)],
        now=NOW,
        active_event=True,
    )
    assert alert["severity"] == "severe"
    assert "CWC's official forecast" in alert["body_en"]


def test_all_clear_after_three_readings_below_danger() -> None:
    alert = evaluate_alert(
        LOCALITY,
        gauge(status="normal", level_m=87.0, trend_cm_per_hr=-5),
        [reading(87.15), reading(87.1), reading(87.0)],
        now=NOW,
        active_event=True,
    )
    assert alert["severity"] == "all_clear"
    assert alert["push"] is True


def test_push_rate_limit_allows_only_severity_increase() -> None:
    previous = {"issued_at": (NOW - timedelta(hours=1)).isoformat(), "severity": "watch"}
    same = evaluate_alert(
        LOCALITY,
        gauge(),
        [reading(87.1), reading(87.3)],
        now=NOW,
        active_event=True,
        previous_push=previous,
    )
    assert same["push"] is False
    severe = evaluate_alert(
        LOCALITY,
        gauge(level_m=89.2),
        [reading(89.0), reading(89.2)],
        now=NOW,
        active_event=True,
        previous_push=previous,
    )
    assert severe["push"] is True


def test_no_data_during_active_event_is_in_app_only() -> None:
    alert = evaluate_alert(
        LOCALITY,
        gauge(status="no_data", level_m=None, data_age_hours=7),
        [],
        now=NOW,
        active_event=True,
    )
    assert alert["severity"] == "info"
    assert alert["push"] is False
    assert "87.3" not in alert["body_en"]


def test_every_alert_persists_three_artifacts(tmp_path: Path) -> None:
    alert = evaluate_alert(
        LOCALITY,
        gauge(),
        [reading(87.1), reading(87.3)],
        now=NOW,
        active_event=False,
    )
    paths = persist_alert_artifacts(alert, output_dir=tmp_path)
    assert set(paths) == {"push", "plain_text", "image_card"}
    assert all(Path(path).exists() for path in paths.values())
    assert Image.open(paths["image_card"]).size == (1080, 1080)
