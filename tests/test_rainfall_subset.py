"""What the Assam subset must refuse before it is allowed to be a rainfall total.

No NASA account exists in CI, so every response here is synthetic. That bounds
what these tests can prove: the slice arithmetic, the ASCII parse, and — the
point of the module — that a wrong grid convention produces a refusal rather
than rain pinned to the wrong place. They cannot prove the live server spells
its variables the way `subset.py` assumes. Only `scripts/smoke_imerg.py
--describe` against a real account can.
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest

from axom_flood.rainfall.imerg import ImergRun, parse_imerg_observations
from axom_flood.rainfall.imerg_client import ImergClient, granule_for
from axom_flood.rainfall.subset import (
    GRID_FIRST_LAT_CENTRE,
    GRID_FIRST_LON_CENTRE,
    GRID_LAT_COUNT,
    GRID_LON_COUNT,
    GridBox,
    SubsetError,
    fetch_subset,
    index_range,
    normalized_payload,
    opendap_base_url,
    parse_ascii_subset,
    payload_bytes,
    subset_request,
)

FETCHED_AT = datetime(2026, 8, 6, 12, 0, tzinfo=UTC)
MOMENT = datetime(2026, 8, 6, 2, 40, tzinfo=UTC)

# A box two cells wide and two cells tall, at a spot with no rounding luck in it.
BOX = GridBox(west=91.3, south=26.4, east=91.5, north=26.6)


def granule():
    return granule_for(MOMENT, run=ImergRun.LATE)


def ascii_response(rows: list[list[float]], *, longitudes, latitudes) -> str:
    """A Hyrax DAP2 ASCII body, in the shape the server documents."""

    lines = [
        "Dataset {",
        f"    Float32 precipitation[time = 1][lon = {len(longitudes)}]"
        f"[lat = {len(latitudes)}];",
        "} 3B-HHR-L.MS.MRG.3IMERG;",
        "---------------------------------------------",
    ]
    for index, row in enumerate(rows):
        values = ", ".join(str(value) for value in row)
        lines.append(f"Grid.precipitation[0][{index}], {values}")
    lines.append("Grid.lon, " + ", ".join(str(value) for value in longitudes))
    lines.append("Grid.lat, " + ", ".join(str(value) for value in latitudes))
    return "\n".join(lines) + "\n"


def two_by_two(values=((1.0, 2.0), (3.0, 4.0))) -> str:
    return ascii_response(
        [list(row) for row in values],
        longitudes=[91.35, 91.45],
        latitudes=[26.45, 26.55],
    )


def test_index_range_rounds_outward_so_no_edge_cell_is_dropped():
    span = index_range(
        91.3, 91.5, first_centre=GRID_FIRST_LON_CENTRE, cell_count=GRID_LON_COUNT
    )
    # Centres 91.35 and 91.45 are indices 2713 and 2714; the range must hold
    # both plus a cell of slack on each side rather than clipping to them.
    assert span.start <= 2713
    assert span.stop >= 2714
    assert span.count >= 2


def test_index_range_is_clamped_to_the_globe():
    span = index_range(
        -179.99, -179.9, first_centre=GRID_FIRST_LON_CENTRE, cell_count=GRID_LON_COUNT
    )
    assert span.start == 0
    top = index_range(
        89.9, 89.99, first_centre=GRID_FIRST_LAT_CENTRE, cell_count=GRID_LAT_COUNT
    )
    assert top.stop == GRID_LAT_COUNT - 1


def test_box_around_cells_covers_the_far_corner_of_the_last_cell():
    box = GridBox.around_cells(["91.3000_26.4000", "91.5000_26.6000"], margin_cells=0)
    assert box.west == pytest.approx(91.3)
    assert box.south == pytest.approx(26.4)
    # The north-east cell extends 0.1 beyond the corner that names it.
    assert box.east == pytest.approx(91.6)
    assert box.north == pytest.approx(26.7)


def test_opendap_url_is_the_archive_url_under_a_different_prefix():
    url = opendap_base_url(granule())
    assert "/opendap/" in url
    assert "/data/" not in url
    assert url.endswith(granule().filename)


def test_request_asks_longitude_before_latitude():
    request = subset_request(granule(), BOX)
    query = request.url.split("?", 1)[1]
    lon_slice = f"{request.longitude_indices}"
    lat_slice = f"{request.latitude_indices}"
    assert f"precipitation[0:0]{lon_slice}{lat_slice}" in query
    assert request.describe_url.endswith(".dmr")


def test_parse_reads_rates_and_names_cells_by_their_corner():
    parsed = parse_ascii_subset(two_by_two(), box=BOX)
    assert parsed.rates_by_cell == {
        "91.3000_26.4000": 1.0,
        "91.3000_26.5000": 2.0,
        "91.4000_26.4000": 3.0,
        "91.4000_26.5000": 4.0,
    }
    assert parsed.missing_cell_ids == ()


def test_fill_values_become_missing_cells_not_zero_rain():
    parsed = parse_ascii_subset(
        two_by_two(((1.0, -9999.9), (3.0, 4.0))), box=BOX
    )
    assert "91.3000_26.5000" not in parsed.rates_by_cell
    assert parsed.missing_cell_ids == ("91.3000_26.5000",)


def test_coordinates_outside_the_requested_box_are_refused():
    text = ascii_response(
        [[1.0, 2.0], [3.0, 4.0]],
        longitudes=[91.35, 91.45],
        # Latitudes from the other side of the equator: what a wrong index
        # convention actually looks like.
        latitudes=[-26.45, -26.55],
    )
    with pytest.raises(SubsetError, match="outside the requested box"):
        parse_ascii_subset(text, box=BOX)


def test_a_response_without_coordinates_is_refused():
    text = "-----\nGrid.precipitation[0][0], 1.0, 2.0\n"
    with pytest.raises(SubsetError, match="no lon/lat arrays"):
        parse_ascii_subset(text, box=BOX)


def test_wrong_dimension_order_is_refused_rather_than_transposed():
    text = ascii_response(
        [[1.0, 2.0, 3.0]],
        longitudes=[91.35, 91.45],
        latitudes=[26.45, 26.55, 26.65],
    )
    with pytest.raises(SubsetError, match="dimension order"):
        parse_ascii_subset(text, box=BOX)


def test_payload_round_trips_into_observations():
    request = subset_request(granule(), BOX)
    parsed = parse_ascii_subset(two_by_two(), box=BOX)
    payload = normalized_payload(parsed, request=request)
    observations = parse_imerg_observations(
        payload_bytes(payload), fetched_at=FETCHED_AT
    )
    assert len(observations) == 4
    first = observations[0]
    assert first.run is ImergRun.LATE
    assert first.interval_end - first.interval_start == request.granule.interval_end - (
        request.granule.interval_start
    )
    # 1 mm/hour over half an hour is half a millimetre, not one.
    assert float(first.accumulated_mm) == pytest.approx(0.5)


def test_payload_keeps_only_the_cells_some_circle_needs():
    request = subset_request(granule(), BOX)
    parsed = parse_ascii_subset(two_by_two(), box=BOX)
    payload = normalized_payload(
        parsed, request=request, keep_cell_ids={"91.3000_26.4000"}
    )
    assert [row["grid_cell_id"] for row in payload["observations"]] == [
        "91.3000_26.4000"
    ]


def test_payload_refuses_when_no_kept_cell_survives():
    request = subset_request(granule(), BOX)
    parsed = parse_ascii_subset(two_by_two(), box=BOX)
    with pytest.raises(SubsetError, match="belongs to any circle"):
        normalized_payload(parsed, request=request, keep_cell_ids={"0.0000_0.0000"})


def test_fetch_records_the_measured_latency_and_stores_normalized_bytes():
    published = "Wed, 06 Aug 2026 16:00:00 GMT"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer token"
        return httpx.Response(
            200, text=two_by_two(), headers={"last-modified": published}
        )

    request = subset_request(granule(), BOX)
    with ImergClient(
        enabled=True, bearer_token="token", transport=httpx.MockTransport(handler)
    ) as client:
        download = fetch_subset(client, request, fetched_at=FETCHED_AT)

    assert download.payload["units"] == "mm/hour"
    assert download.content.endswith(b"\n")
    assert download.revision.sha256
    # The granule ends at 03:00 UTC and the archive says the bytes appeared at
    # 16:00, so the latency is measured at 13 hours rather than assumed at 14.
    assert download.observed_latency_hours == pytest.approx(13.0)


def test_an_empty_body_is_refused():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="   ")

    request = subset_request(granule(), BOX)
    with ImergClient(
        enabled=True, bearer_token="token", transport=httpx.MockTransport(handler)
    ) as client, pytest.raises(SubsetError, match="empty subset"):
        fetch_subset(client, request, fetched_at=FETCHED_AT)
