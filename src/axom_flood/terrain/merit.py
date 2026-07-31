"""MERIT Hydro's existing HAND band manifest and integrity preflight."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from ..rainfall.provenance import GeometryReference, SourceRevision

MERIT_HYDRO_URL = "https://global-hydrodynamics.github.io/MERIT_Hydro/"
MERIT_DATASET_VERSION = "1.0.1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class MeritHandTile:
    tile_id: str
    filename: str
    sha256: str
    byte_length: int
    bounds: tuple[float, float, float, float]

    def __post_init__(self) -> None:
        if not self.tile_id or Path(self.filename).name != self.filename:
            raise ValueError("MERIT tile id and simple filename are required")
        if not _SHA256.fullmatch(self.sha256):
            raise ValueError("MERIT tile sha256 is invalid")
        if self.byte_length <= 4:
            raise ValueError("MERIT tile is too short to be a GeoTIFF")
        west, south, east, north = self.bounds
        if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
            raise ValueError("MERIT tile bounds are invalid")


@dataclass(frozen=True, slots=True)
class MeritHandManifest:
    dataset_version: str
    band: str
    approximate_resolution_m: int
    vertical_units: str
    license_expression: str
    topology_limitation: str
    tiles: tuple[MeritHandTile, ...]
    revision: SourceRevision

    def __post_init__(self) -> None:
        if self.dataset_version != MERIT_DATASET_VERSION:
            raise ValueError("MERIT Hydro dataset version has not been reviewed")
        if self.band != "hnd":
            raise ValueError("MERIT manifest must reference the existing hnd band")
        if self.approximate_resolution_m != 90:
            raise ValueError("MERIT HAND is approximately 90 m, not a 30 m product")
        if self.vertical_units != "metres":
            raise ValueError("MERIT HAND vertical units must be metres")
        if not self.tiles:
            raise ValueError("MERIT HAND manifest must contain tiles")


def parse_merit_hand_manifest(
    content: bytes,
    *,
    fetched_at: datetime,
    source_url: str = MERIT_HYDRO_URL,
) -> MeritHandManifest:
    revision = SourceRevision.capture(
        content,
        source_id="merit-hydro-hand-manifest",
        source_url=source_url,
        fetched_at=fetched_at,
        media_type="application/json",
    )
    try:
        payload = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("MERIT HAND manifest must be UTF-8 JSON") from exc
    if not isinstance(payload, dict) or payload.get("dataset") != "MERIT Hydro":
        raise ValueError("unexpected MERIT HAND dataset identifier")
    rows = payload.get("tiles")
    if not isinstance(rows, list):
        raise ValueError("MERIT HAND manifest tiles must be an array")
    tiles: list[MeritHandTile] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(f"MERIT tile {index} must be an object")
        bounds = row.get("bounds")
        if not isinstance(bounds, list) or len(bounds) != 4:
            raise ValueError(f"MERIT tile {index} bounds must be [west,south,east,north]")
        tiles.append(
            MeritHandTile(
                tile_id=str(row.get("tile_id", "")),
                filename=str(row.get("filename", "")),
                sha256=str(row.get("sha256", "")),
                byte_length=int(row["byte_length"]),
                bounds=tuple(float(item) for item in bounds),
            )
        )
    return MeritHandManifest(
        dataset_version=str(payload.get("dataset_version", "")),
        band=str(payload.get("band", "")),
        approximate_resolution_m=int(payload["approximate_resolution_m"]),
        vertical_units=str(payload.get("vertical_units", "")),
        license_expression=str(payload.get("license_expression", "")),
        topology_limitation=str(payload.get("topology_limitation", "")),
        tiles=tuple(tiles),
        revision=revision,
    )


def preflight_merit_hand_tile(
    path: Path,
    *,
    tile: MeritHandTile,
    manifest: MeritHandManifest,
    aoi_geometry: GeometryReference,
) -> dict[str, Any]:
    """Verify exact existing HAND bytes before any reviewed-AOI clip is scheduled."""

    aoi_geometry.require_reviewed("MERIT HAND tile/AOI preflight")
    if tile not in manifest.tiles:
        raise ValueError("MERIT HAND tile is not part of this manifest revision")
    if path.name != tile.filename:
        raise ValueError("MERIT HAND tile filename does not match the manifest")
    content = path.read_bytes()
    if not content.startswith((b"II*\x00", b"MM\x00*")):
        raise ValueError("MERIT HAND tile does not have a TIFF header")
    if len(content) != tile.byte_length:
        raise ValueError("MERIT HAND tile byte length does not match the manifest")
    digest = hashlib.sha256(content).hexdigest()
    if digest != tile.sha256:
        raise ValueError("MERIT HAND tile digest does not match the manifest")
    return {
        "schema_version": 1,
        "preflight_status": "verified",
        "dataset": "MERIT Hydro",
        "dataset_version": manifest.dataset_version,
        "hand_source": "provided_hnd_band_not_locally_derived",
        "approximate_resolution_m": manifest.approximate_resolution_m,
        "tile_id": tile.tile_id,
        "tile_sha256": tile.sha256,
        "manifest_revision_sha256": manifest.revision.sha256,
        "aoi_geometry": aoi_geometry.as_dict(),
        "topology_limitation": manifest.topology_limitation,
    }
