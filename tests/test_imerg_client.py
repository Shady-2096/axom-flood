"""What the IMERG client must refuse, and what it must record.

No NASA account exists yet, so every response here is synthetic. That limits what
these tests can prove: they prove the refusals, the granule arithmetic, and that
a measured latency is recorded rather than assumed. They do **not** prove the
archive path is right. Only `scripts/smoke_imerg.py` against a real account can.
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest

from axom_flood.rainfall.imd import SourceDisabledError
from axom_flood.rainfall.imerg import IMERG_POLICIES, ImergRun
from axom_flood.rainfall.imerg_client import (
    ImergAuthError,
    ImergClient,
    ImergCredentialsMissing,
    discover_granules,
    granule_for,
)

FETCHED_AT = datetime(2026, 8, 2, 12, 0, tzinfo=UTC)


def transport(handler) -> httpx.MockTransport:
    return httpx.MockTransport(handler)


def ok(headers=None):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"hdf5-bytes", headers=headers or {})

    return handler


# --- refusals ------------------------------------------------------------


def test_a_client_nobody_enabled_refuses_before_touching_the_network():
    with ImergClient() as client, pytest.raises(SourceDisabledError, match="disabled"):
        client.check_configuration()


def test_enabling_without_a_token_names_the_missing_piece():
    with ImergClient(enabled=True) as client, pytest.raises(
        ImergCredentialsMissing, match="no Earthdata bearer token"
    ):
        client.check_configuration()


def test_a_blank_token_is_treated_as_no_token():
    with ImergClient(enabled=True, bearer_token="   ") as client:
        assert client.access_state()["has_token"] is False
        with pytest.raises(ImergCredentialsMissing):
            client.check_configuration()


def test_a_rejected_token_explains_that_the_app_also_needs_authorising():
    def handler(request):
        return httpx.Response(403)

    with ImergClient(
        enabled=True, bearer_token="t", transport=transport(handler)
    ) as client:
        granule = granule_for(FETCHED_AT, run=ImergRun.LATE)
        with pytest.raises(ImergAuthError, match="Authorized Apps"):
            client.fetch_granule(granule, fetched_at=FETCHED_AT)


def test_an_empty_body_is_an_error_and_never_a_dry_half_hour():
    def handler(request):
        return httpx.Response(200, content=b"")

    with ImergClient(
        enabled=True, bearer_token="t", transport=transport(handler)
    ) as client:
        granule = granule_for(FETCHED_AT, run=ImergRun.LATE)
        with pytest.raises(ValueError, match="empty body"):
            client.fetch_granule(granule, fetched_at=FETCHED_AT)


def test_access_state_says_the_path_is_still_unverified():
    with ImergClient() as client:
        state = client.access_state()
    assert state["ready"] is False
    assert state["path_verified_against_live_archive"] is False


# --- granule arithmetic --------------------------------------------------


def test_a_moment_snaps_down_to_the_half_hour_it_falls_in():
    granule = granule_for(datetime(2026, 7, 1, 4, 47, 12, tzinfo=UTC), run=ImergRun.LATE)
    assert granule.interval_start == datetime(2026, 7, 1, 4, 30, tzinfo=UTC)
    assert granule.interval_end == datetime(2026, 7, 1, 5, 0, tzinfo=UTC)


def test_the_filename_carries_the_run_letter_and_minutes_since_midnight():
    granule = granule_for(datetime(2026, 7, 1, 4, 30, tzinfo=UTC), run=ImergRun.LATE)
    assert granule.filename == (
        "3B-HHR-L.MS.MRG.3IMERG.20260701-S043000-E045959.0270.V07C.HDF5"
    )
    early = granule_for(datetime(2026, 7, 1, 0, 0, tzinfo=UTC), run=ImergRun.EARLY)
    assert early.filename.startswith("3B-HHR-E.")
    assert early.filename.split(".")[5] == "0000"


def test_the_url_uses_the_run_s_own_product_and_the_day_of_year():
    granule = granule_for(datetime(2026, 7, 1, 0, 0, tzinfo=UTC), run=ImergRun.EARLY)
    assert IMERG_POLICIES[ImergRun.EARLY].product_short_name in granule.url
    assert "/2026/182/" in granule.url  # 1 July 2026 is day 182


def test_discovery_covers_a_window_with_no_gap_and_no_overlap():
    granules = discover_granules(
        run=ImergRun.LATE,
        window_start=datetime(2026, 7, 1, 0, 0, tzinfo=UTC),
        window_end=datetime(2026, 7, 1, 3, 0, tzinfo=UTC),
    )
    assert len(granules) == 6
    for earlier, later in zip(granules, granules[1:], strict=False):
        assert earlier.interval_end == later.interval_start
    assert granules[-1].interval_end == datetime(2026, 7, 1, 3, 0, tzinfo=UTC)


def test_discovery_refuses_a_backwards_window():
    with pytest.raises(ValueError, match="after window_start"):
        discover_granules(
            run=ImergRun.LATE,
            window_start=datetime(2026, 7, 1, 3, 0, tzinfo=UTC),
            window_end=datetime(2026, 7, 1, 0, 0, tzinfo=UTC),
        )


# --- what a download records ---------------------------------------------


def test_latency_is_measured_from_the_archive_and_not_taken_from_the_policy():
    granule = granule_for(datetime(2026, 7, 1, 0, 0, tzinfo=UTC), run=ImergRun.LATE)
    # Published 20 hours after the observation window closed — well past the
    # documented 14. The measurement must survive the disagreement.
    headers = {
        "last-modified": "Wed, 01 Jul 2026 20:30:00 GMT",
        "etag": '"abc123"',
    }
    with ImergClient(
        enabled=True, bearer_token="t", transport=transport(ok(headers))
    ) as client:
        download = client.fetch_granule(granule, fetched_at=FETCHED_AT)

    assert download.observed_latency_hours == pytest.approx(20.0)
    assert download.published_at_source == "archive_last_modified"
    assert download.etag == '"abc123"'
    record = download.as_dict()
    assert record["documented_typical_latency_hours"] == 14
    assert record["observed_latency_hours"] == pytest.approx(20.0)


def test_a_missing_publication_header_leaves_latency_unknown_not_zero():
    granule = granule_for(datetime(2026, 7, 1, 0, 0, tzinfo=UTC), run=ImergRun.LATE)
    with ImergClient(
        enabled=True, bearer_token="t", transport=transport(ok())
    ) as client:
        download = client.fetch_granule(granule, fetched_at=FETCHED_AT)

    assert download.published_at is None
    assert download.observed_latency_hours is None
    assert download.published_at_source == "unavailable"


def test_the_bytes_are_content_addressed_so_a_reparse_cannot_drift():
    granule = granule_for(datetime(2026, 7, 1, 0, 0, tzinfo=UTC), run=ImergRun.LATE)
    with ImergClient(
        enabled=True, bearer_token="t", transport=transport(ok())
    ) as client:
        download = client.fetch_granule(granule, fetched_at=FETCHED_AT)

    download.revision.verify(download.content)
    assert download.revision.source_id == "nasa-gpm-imerg"
    assert download.revision.byte_length == len(b"hdf5-bytes")


def test_the_token_is_sent_as_a_bearer_header():
    seen = {}

    def handler(request):
        seen["authorization"] = request.headers.get("authorization")
        return httpx.Response(200, content=b"hdf5-bytes")

    granule = granule_for(datetime(2026, 7, 1, 0, 0, tzinfo=UTC), run=ImergRun.LATE)
    with ImergClient(
        enabled=True, bearer_token="secret", transport=transport(handler)
    ) as client:
        client.fetch_granule(granule, fetched_at=FETCHED_AT)

    assert seen["authorization"] == "Bearer secret"
