from datetime import datetime
from zoneinfo import ZoneInfo


def test_stale_reference_timestamp_is_older_than_current_phase() -> None:
    issued = datetime(2023, 8, 26, 9, 41, tzinfo=ZoneInfo("Asia/Kolkata"))
    now = datetime(2026, 7, 26, tzinfo=ZoneInfo("Asia/Kolkata"))
    assert (now - issued).total_seconds() / 3600 > 24
