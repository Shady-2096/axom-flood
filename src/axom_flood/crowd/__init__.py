"""Phase 2 crowd reports: anonymous ground-truth reports from the field.

The privacy guarantees for this module are the reason it exists and are
enforced by tests under ``tests/test_crowd.py``. Two of them are invariants
that hold at every point in the data path after intake:

1. No coordinate more precise than the rounding step is ever stored or
   transmitted. The full-precision GPS reading is consumed only to compute
   the rounded cell and is then discarded.
2. No PII of any kind &mdash; name, phone, email, raw device token, or
   full-precision coordinate &mdash; appears in any field of a stored or
   published record.

See ``assam-flood-implementation-plan.md`` PART 3 §3.5 and PART 4 Phase 2.
"""

from __future__ import annotations

from .pipeline import (
    ingest_crowd_inbox,
    ingest_crowd_submission,
    ingest_high_water_mark,
    load_month_salt,
    publish_high_water_mark_set,
    publish_open_dataset,
)
from .privacy import (
    MIN_PRECISION_M,
    PrivacyError,
    assert_no_pii,
    device_hash,
    month_string,
    round_coordinate,
    serialise_for_audit,
)

__all__ = [
    "MIN_PRECISION_M",
    "PrivacyError",
    "assert_no_pii",
    "device_hash",
    "ingest_crowd_inbox",
    "ingest_crowd_submission",
    "ingest_high_water_mark",
    "load_month_salt",
    "month_string",
    "publish_high_water_mark_set",
    "publish_open_dataset",
    "round_coordinate",
    "serialise_for_audit",
]