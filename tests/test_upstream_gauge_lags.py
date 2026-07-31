from __future__ import annotations

import json
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from axom_flood.cwc.client import IST
from axom_flood.cwc.history import HistoryAudit, HistorySeries, Observation
from axom_flood.hydrology import lag
from axom_flood.hydrology import pipeline as lag_pipeline

ROOT = Path(__file__).resolve().parents[1]


def _audit(count: int) -> HistoryAudit:
    return HistoryAudit(
        rows_seen=count,
        observations_accepted=count,
        foreign_datatype_rows=0,
        wrong_station_rows=0,
        malformed_rows=0,
        implausible_rows=0,
        duplicate_rows_collapsed=0,
        corrections_applied=0,
        ambiguous_timestamps=0,
        ambiguous_timestamp_examples=(),
    )


def _synthetic_pair(
    years: list[int],
    *,
    lag_hours: int,
) -> tuple[HistorySeries, HistorySeries]:
    upstream: list[Observation] = []
    downstream: list[Observation] = []
    for year in years:
        start = datetime(year, 4, 20, tzinfo=IST)
        hours = 24 * 75
        randomizer = random.Random(year)
        level = 100.0
        values: dict[datetime, float] = {}
        for hour in range(hours):
            observed_at = start + timedelta(hours=hour)
            pulse = 0.35 if hour % 191 in {0, 1, 2} else 0.0
            recession = -0.12 if hour % 191 in {12, 13, 14} else 0.0
            level += randomizer.uniform(-0.04, 0.04) + pulse + recession
            values[observed_at] = level
            upstream.append(Observation(observed_at, level, "synthetic"))
        offset = timedelta(hours=lag_hours)
        for observed_at in sorted(values):
            source_at = observed_at - offset
            if source_at in values:
                downstream.append(
                    Observation(
                        observed_at,
                        40.0 + values[source_at] - 100.0,
                        "synthetic",
                    )
                )
    return (
        HistorySeries(
            "UP",
            tuple(upstream),
            _audit(len(upstream)),
            "synthetic-upstream",
            "a" * 64,
        ),
        HistorySeries(
            "DOWN",
            tuple(downstream),
            _audit(len(downstream)),
            "synthetic-downstream",
            "b" * 64,
        ),
    )


@pytest.fixture
def reduced_quality_gates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(lag, "MAX_LAG_HOURS", 24)
    monkeypatch.setattr(lag, "MIN_MONSOON_COVERAGE", 0.2)
    monkeypatch.setattr(lag, "MIN_ACTIVE_PAIRS", 100)
    monkeypatch.setattr(lag, "MIN_RISE_EVENTS", 2)
    monkeypatch.setattr(lag, "MIN_COMPLETED_YEARS", 3)
    monkeypatch.setattr(lag, "MIN_ROBUST_CORRELATION", 0.8)
    monkeypatch.setattr(lag, "MIN_CORRELATED_YEAR_FRACTION", 1.0)
    monkeypatch.setattr(lag, "MAX_STABLE_DEVIATION_HOURS", 2)
    monkeypatch.setattr(lag, "MIN_STABLE_YEAR_FRACTION", 1.0)
    monkeypatch.setattr(lag, "MAX_LAG_IQR_HOURS", 2)
    monkeypatch.setattr(lag, "MIN_ZERO_LAG_IMPROVEMENT", 0.1)


def test_stable_multiyear_lag_passes_but_incomplete_monsoon_is_excluded(
    reduced_quality_gates: None,
) -> None:
    upstream, downstream = _synthetic_pair(
        [2022, 2023, 2024, 2026],
        lag_hours=12,
    )

    result = lag.analyze_relationship(
        upstream,
        downstream,
        now=datetime(2026, 7, 29, tzinfo=IST),
    )

    assert result["quality"]["passes_quality_gates"] is True
    assert result["quality"]["recommended_lag_hours"] == 12.0
    assert result["quality"]["eligible_completed_years"] == 3
    current = next(item for item in result["year_results"] if item["year"] == 2026)
    assert current["complete_year"] is False
    assert current["eligible_for_stability"] is False
    assert "monsoon_year_in_progress" in current["ineligible_reasons"]


def test_synchronous_series_fails_positive_lead_and_zero_lag_gates(
    reduced_quality_gates: None,
) -> None:
    upstream, downstream = _synthetic_pair([2022, 2023, 2024], lag_hours=0)

    result = lag.analyze_relationship(
        upstream,
        downstream,
        now=datetime(2026, 7, 29, tzinfo=IST),
    )

    assert result["quality"]["recommended_lag_hours"] == 0.0
    assert result["quality"]["gates"]["positive_lead_time"] is False
    assert result["quality"]["gates"]["improves_on_zero_lag"] is False
    assert result["quality"]["passes_quality_gates"] is False


def _raw_history_row(code: str) -> dict[str, Any]:
    return {
        "id": {
            "stationCode": code,
            "datatypeCode": "HHS",
            "dataTime": "2024-06-01T12:00:00",
        },
        "dataValue": 100.0,
    }


def _analysis_stub() -> dict[str, Any]:
    return {
        "method": "test_method",
        "change_window_hours": 6,
        "lag_search_hours": [0, 72],
        "quality_gate_thresholds": {},
        "robustness": "test",
        "quality": {
            "passes_quality_gates": True,
        },
        "year_results": [],
    }


def _validate(document: dict[str, Any], schema_name: str) -> None:
    schema = json.loads((ROOT / "schemas" / schema_name).read_text())
    Draft202012Validator(
        schema,
        format_checker=FormatChecker(),
    ).validate(document)


def test_pipeline_can_only_emit_review_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_dir = tmp_path / "data"
    cache = data_dir / "cache" / "cwc-history"
    cache.mkdir(parents=True)
    for code in ("UP", "DOWN"):
        (cache / f"{code}.json").write_text(json.dumps([_raw_history_row(code)]))
    config = {
        "schema_version": 1,
        "purpose": "test review only",
        "relationships": [
            {
                "relationship_id": "up-to-down",
                "upstream_station_code": "UP",
                "downstream_station_code": "DOWN",
                "topology_status": "candidate_unreviewed",
                "topology_basis": "test-only unreviewed topology",
            }
        ],
    }
    config_path = tmp_path / "candidates.json"
    config_path.write_text(json.dumps(config))
    monkeypatch.setattr(
        lag_pipeline,
        "analyze_relationship",
        lambda *args, **kwargs: _analysis_stub(),
    )

    review = lag_pipeline.build_review(
        data_dir=data_dir,
        config_path=config_path,
        now=datetime(2026, 7, 29, tzinfo=IST),
    )

    relationship = review["relationships"][0]
    assert review["review_only"] is True
    assert relationship["disposition"] == "evidence_supports_hydrology_review"
    assert relationship["automatic_use_allowed"] is False
    assert relationship["mapping_changed"] is False
    assert relationship["topology"]["review_required"] is True
    assert relationship["topology"]["reviewed_by"] is None
    _validate(review, "upstream-gauge-lag-review.schema.json")


def test_artifact_is_immutable_and_pointer_is_portable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_dir = tmp_path / "data"
    cache = data_dir / "cache" / "cwc-history"
    cache.mkdir(parents=True)
    for code in ("UP", "DOWN"):
        (cache / f"{code}.json").write_text(json.dumps([_raw_history_row(code)]))
    config_path = tmp_path / "candidates.json"
    config_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "purpose": "test review only",
                "relationships": [
                    {
                        "relationship_id": "up-to-down",
                        "upstream_station_code": "UP",
                        "downstream_station_code": "DOWN",
                        "topology_status": "hypothesis_unverified",
                        "topology_basis": "test-only unverified topology",
                    }
                ],
            }
        )
    )
    monkeypatch.setattr(
        lag_pipeline,
        "analyze_relationship",
        lambda *args, **kwargs: _analysis_stub(),
    )
    review = lag_pipeline.build_review(
        data_dir=data_dir,
        config_path=config_path,
        now=datetime(2026, 7, 29, tzinfo=IST),
    )
    output = tmp_path / "review"

    first = lag_pipeline.persist_review(review, output_dir=output)
    second = lag_pipeline.persist_review(review, output_dir=output)
    pointer = json.loads(Path(first["pointer"]).read_text())

    assert first["artifact_id"] == second["artifact_id"]
    assert pointer["artifact_path"] == f"{first['artifact_id']}.json"
    _validate(pointer, "upstream-gauge-lag-pointer.schema.json")

    Path(first["json"]).write_text("tampered")
    with pytest.raises(RuntimeError, match="refusing to overwrite immutable artifact"):
        lag_pipeline.persist_review(review, output_dir=output)


def test_checked_in_candidate_config_is_review_only_and_schema_valid() -> None:
    config = json.loads((ROOT / "config" / "upstream-gauge-candidates.json").read_text())

    _validate(config, "upstream-gauge-candidates.schema.json")
    assert {
        item["topology_status"] for item in config["relationships"]
    } <= {"candidate_unreviewed", "hypothesis_unverified"}
