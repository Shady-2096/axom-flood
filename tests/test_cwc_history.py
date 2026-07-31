from __future__ import annotations

import hashlib
import json
from pathlib import Path

from axom_flood.cwc.history import load_cached_history, resolve_history_rows

STATION = "TEST-001"


def _row(
    observed_at: str,
    raw: object,
    *,
    validated: object = None,
    station: str = STATION,
    datatype: str = "HHS",
) -> dict[str, object]:
    row: dict[str, object] = {
        "id": {
            "stationCode": station,
            "datatypeCode": datatype,
            "dataTime": observed_at,
        },
        "dataValue": raw,
    }
    if validated is not None:
        row["dataValidatedValue"] = validated
    return row


def test_validated_correction_wins_independent_of_row_order() -> None:
    timestamp = "2024-06-01T12:00:00"
    rows = [
        _row(timestamp, "101.20"),
        _row(timestamp, "101.20", validated="101.45"),
    ]

    forward, forward_audit = resolve_history_rows(rows, station_code=STATION)
    reverse, reverse_audit = resolve_history_rows(reversed(rows), station_code=STATION)

    assert forward == reverse
    assert len(forward) == 1
    assert forward[0].level_m == 101.45
    assert forward[0].value_source == "validated"
    assert forward_audit.corrections_applied == 1
    assert reverse_audit.corrections_applied == 1
    assert forward_audit.duplicate_rows_collapsed == 1


def test_conflicting_unvalidated_rows_are_excluded() -> None:
    timestamp = "2024-06-01T12:00:00"
    observations, audit = resolve_history_rows(
        [_row(timestamp, 101.2), _row(timestamp, 102.2)],
        station_code=STATION,
    )

    assert observations == ()
    assert audit.ambiguous_timestamps == 1
    assert audit.ambiguous_timestamp_examples == (
        "2024-06-01T12:00:00+05:30",
    )


def test_conflicting_validated_rows_are_excluded_even_when_raw_matches() -> None:
    timestamp = "2024-06-01T12:00:00"
    observations, audit = resolve_history_rows(
        [
            _row(timestamp, 101.2, validated=101.3),
            _row(timestamp, 101.2, validated=101.4),
        ],
        station_code=STATION,
    )

    assert observations == ()
    assert audit.ambiguous_timestamps == 1


def test_equivalent_duplicates_collapse_and_invalid_rows_are_audited() -> None:
    valid_time = "2024-06-01T12:00:00"
    observations, audit = resolve_history_rows(
        [
            _row(valid_time, "101.20"),
            _row(valid_time, 101.2),
            _row("not-a-date", 100),
            _row("2024-06-01T12:30:00", 100),
            _row("2024-06-01T13:00:00", -999),
            _row("2024-06-01T14:00:00", 100, station="OTHER"),
            _row("2024-06-01T15:00:00", 100, datatype="HZS"),
        ],
        station_code=STATION,
    )

    assert len(observations) == 1
    assert audit.rows_seen == 7
    assert audit.observations_accepted == 1
    assert audit.duplicate_rows_collapsed == 1
    assert audit.malformed_rows == 1
    assert audit.implausible_rows == 2
    assert audit.wrong_station_rows == 1
    assert audit.foreign_datatype_rows == 1


def test_cached_history_retains_raw_content_hash(tmp_path: Path) -> None:
    path = tmp_path / f"{STATION}.json"
    body = json.dumps([_row("2024-06-01T12:00:00", 101.2)]).encode()
    path.write_bytes(body)

    history = load_cached_history(path)

    assert history.station_code == STATION
    assert history.source_sha256 == hashlib.sha256(body).hexdigest()
    assert history.audit.observations_accepted == 1
    assert history.provenance()["source_path"] == str(path)
