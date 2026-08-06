"""Ask NASA for Assam only, and turn the answer into grid observations.

Workstream C's missing middle. `imerg_client.py` can name and download a granule;
`imerg.py` can parse a normalized payload; `zonal.py` can turn a grid into a
circle number. Nothing joined the download to the parse, because a downloaded
granule is a global HDF5 file and this project has never had a reader for one.

Why a server-side subset rather than a global file
--------------------------------------------------

A half-hourly IMERG granule covers the whole planet. Assam is 518 of its cells.
A 72-hour window is 144 granules, so downloading whole granules to keep 0.04% of
each one turns a few megabytes of useful rain into gigabytes of transfer, every
two hours, forever. GES DISC runs an OPeNDAP server that will cut the box out
before sending it, which is both the cheap path and the one the plan asks for:
"immutable daily Assam subsets, not global grids".

It also removes a dependency. Reading HDF5 locally means h5py and numpy, two
compiled wheels, in a project whose entire runtime is httpx and a JSON parser.
The subset arrives as text.

⚠️ Unverified until the smoke test runs
---------------------------------------

The variable path, the response flavour, and the index convention below are
written from NASA's published grid documentation and Hyrax's documented ASCII
format. None of it has been confirmed against the live archive, because that
needs an Earthdata account. `scripts/smoke_imerg.py --subset` is the one command
that confirms it, and `--describe` prints the server's own variable listing so a
mismatch is read off the server rather than guessed at.

The one guard that makes an unverified index convention safe
------------------------------------------------------------

Cell coordinates are never computed from the array index. They are read from the
`lon` and `lat` arrays the server sends back with the data. The index arithmetic
here only decides *which* slice to ask for; if the convention is wrong, the
returned coordinates land outside the box we asked about, and `parse_ascii_subset`
refuses the whole subset. A wrong guess therefore produces a refusal, never a
rainfall total pinned to the wrong place.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from math import floor
from typing import Any

from .imerg import IMERG_POLICIES, ImergRun
from .imerg_client import ImergClient, ImergGranule, publication_time
from .provenance import SourceRevision, require_aware
from .zonal import grid_cell_id

#: The IMERG V07 global grid, from NASA's product documentation: 3600 × 1800
#: cells of 0.1°, with the first cell *centred* at (-179.95, -89.95). Centres,
#: not corners — the half-cell offset is the classic way to be one cell out.
GRID_CELL_DEGREES = 0.1
GRID_FIRST_LON_CENTRE = -179.95
GRID_FIRST_LAT_CENTRE = -89.95
GRID_LON_COUNT = 3600
GRID_LAT_COUNT = 1800

#: The precipitation field, and the two coordinate arrays that must come back
#: with it. IMERG V07 puts everything under a `Grid` group; OPeNDAP flattens
#: group paths, and the exact spelling is what `--describe` is for.
DEFAULT_VARIABLE = "Grid/precipitation"
DEFAULT_LON_VARIABLE = "Grid/lon"
DEFAULT_LAT_VARIABLE = "Grid/lat"

#: GES DISC serves the same files over OPeNDAP as over plain HTTP, under a
#: different path prefix.
OPENDAP_BASE = "https://gpm1.gesdisc.eosdis.nasa.gov/opendap"
ARCHIVE_PATH_PREFIX = "/data/"
OPENDAP_PATH_PREFIX = "/opendap/"

#: IMERG marks "no retrieval here" with a large negative number rather than a
#: gap. Treating it as rainfall would be absurd; treating it as zero would be
#: worse, because zero is a claim that it did not rain.
FILL_THRESHOLD_MM_PER_HOUR = -0.0001

#: How far a returned coordinate may sit outside the requested box before the
#: subset is refused. One cell absorbs the difference between naming a cell by
#: its corner and by its centre; anything more is a real disagreement.
_BOX_TOLERANCE_DEGREES = GRID_CELL_DEGREES * 1.5


class SubsetError(ValueError):
    """The server's answer cannot be trusted to mean what we asked for."""


@dataclass(frozen=True, slots=True)
class GridBox:
    """A geographic box, in degrees, that a subset request covers."""

    west: float
    south: float
    east: float
    north: float

    def __post_init__(self) -> None:
        if self.east <= self.west or self.north <= self.south:
            raise ValueError("a grid box needs east > west and north > south")
        if not -180 <= self.west < self.east <= 180:
            raise ValueError("grid box longitudes are out of range")
        if not -90 <= self.south < self.north <= 90:
            raise ValueError("grid box latitudes are out of range")

    @classmethod
    def around_cells(
        cls,
        cell_ids: list[str],
        *,
        cell_degrees: float = GRID_CELL_DEGREES,
        margin_cells: int = 1,
    ) -> GridBox:
        """The smallest box holding every named cell, plus a margin.

        The margin is not decoration. Cell ids name south-west corners, so the
        northernmost cell extends one cell further north than its own name, and
        a server that rounds a slice bound the other way would clip it off.
        """

        if not cell_ids:
            raise ValueError("no cells were given to bound")
        corners = [_parse_cell_id(cell_id) for cell_id in cell_ids]
        pad = cell_degrees * margin_cells
        return cls(
            west=min(corner[0] for corner in corners) - pad,
            south=min(corner[1] for corner in corners) - pad,
            east=max(corner[0] for corner in corners) + cell_degrees + pad,
            north=max(corner[1] for corner in corners) + cell_degrees + pad,
        )

    def holds_longitude(self, longitude: float) -> bool:
        return (
            self.west - _BOX_TOLERANCE_DEGREES
            <= longitude
            <= self.east + _BOX_TOLERANCE_DEGREES
        )

    def holds_latitude(self, latitude: float) -> bool:
        return (
            self.south - _BOX_TOLERANCE_DEGREES
            <= latitude
            <= self.north + _BOX_TOLERANCE_DEGREES
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "west": round(self.west, 4),
            "south": round(self.south, 4),
            "east": round(self.east, 4),
            "north": round(self.north, 4),
        }


def _parse_cell_id(cell_id: str) -> tuple[float, float]:
    try:
        west, south = cell_id.split("_")
        return float(west), float(south)
    except ValueError as exc:
        raise ValueError(f"{cell_id!r} is not a grid cell id") from exc


@dataclass(frozen=True, slots=True)
class IndexRange:
    """An inclusive OPeNDAP slice, in array index space."""

    start: int
    stop: int

    def __post_init__(self) -> None:
        if self.start < 0 or self.stop < self.start:
            raise ValueError("an index range must be non-negative and ordered")

    @property
    def count(self) -> int:
        return self.stop - self.start + 1

    def __str__(self) -> str:
        return f"[{self.start}:{self.stop}]"


def index_range(
    low: float,
    high: float,
    *,
    first_centre: float,
    cell_count: int,
) -> IndexRange:
    """Every array index whose cell centre could fall in [low, high].

    Rounded outward on both ends. A subset that is one cell too wide costs a
    kilobyte; one that is one cell too narrow silently drops a circle's edge
    cell, and `zonal.py` then refuses the whole circle for missing coverage.
    """

    start = floor(round((low - first_centre) / GRID_CELL_DEGREES, 6))
    stop = floor(round((high - first_centre) / GRID_CELL_DEGREES, 6)) + 1
    return IndexRange(start=max(0, start), stop=min(cell_count - 1, stop))


@dataclass(frozen=True, slots=True)
class SubsetRequest:
    """One granule, cut down to one box, and the URLs that say so."""

    granule: ImergGranule
    box: GridBox
    longitude_indices: IndexRange
    latitude_indices: IndexRange
    variable: str
    url: str
    describe_url: str

    @property
    def cell_count(self) -> int:
        return self.longitude_indices.count * self.latitude_indices.count

    def as_dict(self) -> dict[str, Any]:
        return {
            "granule": self.granule.as_dict(),
            "box": self.box.as_dict(),
            "variable": self.variable,
            "longitude_indices": [
                self.longitude_indices.start,
                self.longitude_indices.stop,
            ],
            "latitude_indices": [
                self.latitude_indices.start,
                self.latitude_indices.stop,
            ],
            "requested_cells": self.cell_count,
            "url": self.url,
            "describe_url": self.describe_url,
            "path_verified_against_live_archive": False,
        }


def opendap_base_url(granule: ImergGranule) -> str:
    """The OPeNDAP address of the same file the archive serves over HTTP."""

    if ARCHIVE_PATH_PREFIX in granule.url:
        return granule.url.replace(ARCHIVE_PATH_PREFIX, OPENDAP_PATH_PREFIX, 1)
    product = IMERG_POLICIES[granule.run].product_short_name
    day = granule.interval_start.timetuple().tm_yday
    return (
        f"{OPENDAP_BASE}/GPM_L3/{product}/"
        f"{granule.interval_start:%Y}/{day:03d}/{granule.filename}"
    )


def subset_request(
    granule: ImergGranule,
    box: GridBox,
    *,
    variable: str = DEFAULT_VARIABLE,
    lon_variable: str = DEFAULT_LON_VARIABLE,
    lat_variable: str = DEFAULT_LAT_VARIABLE,
) -> SubsetRequest:
    """Name the slice of one granule that covers a box, without fetching it."""

    lon_indices = index_range(
        box.west, box.east, first_centre=GRID_FIRST_LON_CENTRE, cell_count=GRID_LON_COUNT
    )
    lat_indices = index_range(
        box.south, box.north, first_centre=GRID_FIRST_LAT_CENTRE, cell_count=GRID_LAT_COUNT
    )
    base = opendap_base_url(granule)
    # IMERG's precipitation field is [time][lon][lat]: longitude before
    # latitude, which is the opposite of most gridded products and the single
    # easiest thing to get backwards here. The lon/lat arrays that come back
    # with the slice are what proves the order was right.
    query = (
        f"{variable}[0:0]{lon_indices}{lat_indices},"
        f"{lon_variable}{lon_indices},"
        f"{lat_variable}{lat_indices}"
    )
    return SubsetRequest(
        granule=granule,
        box=box,
        longitude_indices=lon_indices,
        latitude_indices=lat_indices,
        variable=variable,
        url=f"{base}.ascii?{query}",
        describe_url=f"{base}.dmr",
    )


_LABEL_SPLIT = re.compile(r"^(?P<label>[^,\[]+)(?P<indices>(\[\d+\])*)\s*,\s*(?P<values>.*)$")
_SEPARATOR = re.compile(r"^-{5,}\s*$")


def _leaf_name(label: str) -> str:
    """The last path element of an OPeNDAP name, however the server spelled it.

    Hyrax has flattened group paths as `Grid_precipitation`, `Grid.precipitation`
    and `/Grid/precipitation` across versions, and DAP2 additionally prefixes a
    grid's array with the grid's own name. Comparing leaves rather than full
    paths means a server-side rename is not an outage.
    """

    leaf = label.strip().strip("/")
    for character in ("/", ".", "_"):
        leaf = leaf.rsplit(character, 1)[-1]
    return leaf


def _numbers(raw: str) -> list[float]:
    values: list[float] = []
    for chunk in raw.split(","):
        text = chunk.strip()
        if not text:
            continue
        try:
            values.append(float(text))
        except ValueError as exc:
            raise SubsetError(f"{text!r} is not a number in the ASCII response") from exc
    return values


@dataclass(frozen=True, slots=True)
class ParsedSubset:
    """What the server actually sent: coordinates, and rates keyed by cell."""

    longitudes: tuple[float, ...]
    latitudes: tuple[float, ...]
    rates_by_cell: dict[str, float]
    missing_cell_ids: tuple[str, ...]

    @property
    def cell_count(self) -> int:
        return len(self.rates_by_cell)


def parse_ascii_subset(text: str, *, box: GridBox) -> ParsedSubset:
    """Read a Hyrax DAP2 ASCII response into rates, or refuse it.

    Every refusal here is a case where continuing would produce a plausible
    number attached to the wrong place or the wrong time.
    """

    body = text
    for line in text.splitlines():
        if _SEPARATOR.match(line):
            body = text.split(line, 1)[1]
            break

    rows: dict[str, list[list[float]]] = {}
    for line in body.splitlines():
        line = line.strip()
        if not line or line.startswith(("Dataset", "}", "{")):
            continue
        match = _LABEL_SPLIT.match(line)
        if not match:
            continue
        leaf = _leaf_name(match.group("label"))
        rows.setdefault(leaf, []).append(_numbers(match.group("values")))

    longitudes = [value for row in rows.get("lon", []) for value in row]
    latitudes = [value for row in rows.get("lat", []) for value in row]
    if not longitudes or not latitudes:
        raise SubsetError(
            "the response carried no lon/lat arrays, so no reading can be placed "
            "on the ground; coordinates are never inferred from array indices"
        )

    grid = rows.get("precipitation")
    if not grid:
        raise SubsetError("the response carried no precipitation array")
    if len(grid) != len(longitudes):
        raise SubsetError(
            f"the precipitation array has {len(grid)} rows but {len(longitudes)} "
            "longitudes; the dimension order is not [time][lon][lat] as assumed"
        )

    outside = [value for value in longitudes if not box.holds_longitude(value)]
    outside += [value for value in latitudes if not box.holds_latitude(value)]
    if outside:
        raise SubsetError(
            f"{len(outside)} returned coordinates fall outside the requested box; "
            "the grid index convention is wrong and the slice is of somewhere else"
        )

    rates: dict[str, float] = {}
    missing: list[str] = []
    for lon_index, row in enumerate(grid):
        if len(row) != len(latitudes):
            raise SubsetError(
                f"precipitation row {lon_index} has {len(row)} values but "
                f"{len(latitudes)} latitudes were returned"
            )
        for lat_index, value in enumerate(row):
            cell = grid_cell_id(
                longitudes[lon_index], latitudes[lat_index], GRID_CELL_DEGREES
            )
            if value < FILL_THRESHOLD_MM_PER_HOUR:
                missing.append(cell)
                continue
            rates[cell] = value

    return ParsedSubset(
        longitudes=tuple(longitudes),
        latitudes=tuple(latitudes),
        rates_by_cell=rates,
        missing_cell_ids=tuple(sorted(set(missing))),
    )


def normalized_payload(
    parsed: ParsedSubset,
    *,
    request: SubsetRequest,
    keep_cell_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Turn a parsed subset into the payload `parse_imerg_observations` accepts.

    `keep_cell_ids` drops the cells no circle needs. The box is a rectangle and
    Assam is not, so roughly half of what comes back belongs to no circle at all
    and only makes the stored artifact bigger.
    """

    run: ImergRun = request.granule.run
    observations = []
    for cell_id, rate in sorted(parsed.rates_by_cell.items()):
        if keep_cell_ids is not None and cell_id not in keep_cell_ids:
            continue
        west, south = _parse_cell_id(cell_id)
        observations.append(
            {
                "grid_cell_id": cell_id,
                "longitude": round(west + GRID_CELL_DEGREES / 2, 4),
                "latitude": round(south + GRID_CELL_DEGREES / 2, 4),
                "interval_start": request.granule.interval_start.isoformat(),
                "interval_end": request.granule.interval_end.isoformat(),
                "precipitation_rate": rate,
            }
        )
    if not observations:
        raise SubsetError(
            "no cell in this subset belongs to any circle; the box and the zone "
            "weights disagree about where Assam is"
        )
    return {
        "schema_version": 1,
        "record": "imerg_assam_subset",
        "run": run.value,
        "product_short_name": IMERG_POLICIES[run].product_short_name,
        "product_version": "07",
        "version_suffix": request.granule.version_suffix,
        "units": "mm/hour",
        "box": request.box.as_dict(),
        "source_url": request.url,
        "missing_cell_ids": [
            cell_id
            for cell_id in parsed.missing_cell_ids
            if keep_cell_ids is None or cell_id in keep_cell_ids
        ],
        "missing_note": (
            "cells IMERG marked as no-retrieval. They are absent rather than "
            "zero, so a window covering them is refused instead of under-reported."
        ),
        "observations": observations,
    }


def payload_bytes(payload: dict[str, Any]) -> bytes:
    """Serialize a payload the one way, so its digest is its identity."""

    return json.dumps(payload, indent=2, sort_keys=True).encode() + b"\n"


@dataclass(frozen=True, slots=True)
class SubsetDownload:
    """One granule's Assam box, as stored: payload, identity, and timing."""

    request: SubsetRequest
    payload: dict[str, Any]
    content: bytes
    revision: SourceRevision
    published_at: datetime | None
    published_at_source: str
    observed_latency_hours: float | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "request": self.request.as_dict(),
            "revision": self.revision.as_dict(),
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "published_at_source": self.published_at_source,
            "observed_latency_hours": self.observed_latency_hours,
            "documented_typical_latency_hours": IMERG_POLICIES[
                self.request.granule.run
            ].typical_latency_hours,
            "observation_count": len(self.payload["observations"]),
            "missing_cell_count": len(self.payload["missing_cell_ids"]),
        }


def fetch_subset(
    client: ImergClient,
    request: SubsetRequest,
    *,
    fetched_at: datetime,
    keep_cell_ids: set[str] | None = None,
) -> SubsetDownload:
    """Ask the archive for one box of one granule and normalize what comes back.

    The stored bytes are our normalized payload, not the server's ASCII. The
    ASCII is a Hyrax response format that can change spelling between server
    versions; the payload is a contract this repository owns and tests. The
    response URL travels inside the payload so the original request is still
    recoverable from the artifact.
    """

    require_aware(fetched_at, "fetched_at")
    response = client.get(request.url)
    text = response.text
    if not text.strip():
        raise SubsetError(f"{request.granule.filename} returned an empty subset")

    parsed = parse_ascii_subset(text, box=request.box)
    payload = normalized_payload(parsed, request=request, keep_cell_ids=keep_cell_ids)
    content = payload_bytes(payload)

    published_at, published_source = publication_time(response)
    latency = None
    if published_at is not None:
        latency = round(
            (published_at - request.granule.interval_end).total_seconds() / 3600, 3
        )

    return SubsetDownload(
        request=request,
        payload=payload,
        content=content,
        revision=SourceRevision.capture(
            content,
            source_id="nasa-gpm-imerg-assam-subset",
            source_url=str(response.url),
            fetched_at=fetched_at,
            media_type="application/json",
        ),
        published_at=published_at,
        published_at_source=published_source,
        observed_latency_hours=latency,
    )
