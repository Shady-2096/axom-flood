"""Sentinel-1 retrospective scene manifests and event association.

The scaffold records scene identity and timing but does not call thresholded SAR
pixels "flood extent". Spatial coverage must be associated through a reviewed
AOI, and the resulting record remains retrospective validation evidence.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ..rainfall.provenance import (
    GeometryReference,
    SourceRevision,
    parse_aware_datetime,
    require_aware,
)

SENTINEL_1_COLLECTION_URL = (
    "https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_S1_GRD"
)


@dataclass(frozen=True, slots=True)
class SentinelSceneManifest:
    scene_id: str
    collection: str
    acquisition_start: datetime
    acquisition_end: datetime
    instrument_mode: str
    orbit_pass: str
    relative_orbit_number: int
    polarizations: tuple[str, ...]
    nominal_resolution_m: int
    asset_url: str
    revision: SourceRevision

    def __post_init__(self) -> None:
        require_aware(self.acquisition_start, "acquisition_start")
        require_aware(self.acquisition_end, "acquisition_end")
        if self.acquisition_end < self.acquisition_start:
            raise ValueError("Sentinel acquisition end precedes start")
        if self.collection != "COPERNICUS/S1_GRD":
            raise ValueError("only the reviewed Sentinel-1 GRD collection is accepted")
        if self.instrument_mode != "IW":
            raise ValueError("Assam retrospective scaffold accepts IW scenes only")
        if self.orbit_pass not in {"ASCENDING", "DESCENDING"}:
            raise ValueError("Sentinel orbit_pass must be ASCENDING or DESCENDING")
        if not set(self.polarizations).issubset({"VV", "VH", "HH", "HV"}):
            raise ValueError("Sentinel manifest contains an unknown polarization")
        if not self.polarizations:
            raise ValueError("Sentinel manifest must list polarizations")
        if self.nominal_resolution_m not in {10, 25, 40}:
            raise ValueError("Sentinel GRD nominal resolution is not recognized")


@dataclass(frozen=True, slots=True)
class FloodEventWindow:
    event_id: str
    starts_at: datetime
    ends_at: datetime
    evidence_revision_sha256: str

    def __post_init__(self) -> None:
        require_aware(self.starts_at, "starts_at")
        require_aware(self.ends_at, "ends_at")
        if self.ends_at < self.starts_at:
            raise ValueError("flood event ends before it starts")
        if len(self.evidence_revision_sha256) != 64:
            raise ValueError("event evidence revision must be a SHA-256 digest")


def parse_sentinel_scene_manifest(
    content: bytes,
    *,
    fetched_at: datetime,
    source_url: str = SENTINEL_1_COLLECTION_URL,
) -> SentinelSceneManifest:
    revision = SourceRevision.capture(
        content,
        source_id="copernicus-sentinel-1-grd-manifest",
        source_url=source_url,
        fetched_at=fetched_at,
        media_type="application/json",
    )
    try:
        payload = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Sentinel scene manifest must be UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("Sentinel scene manifest must be an object")
    polarizations = payload.get("polarizations")
    if not isinstance(polarizations, list):
        raise ValueError("Sentinel polarizations must be an array")
    return SentinelSceneManifest(
        scene_id=str(payload.get("scene_id", "")),
        collection=str(payload.get("collection", "")),
        acquisition_start=parse_aware_datetime(
            payload.get("acquisition_start", ""), "acquisition_start"
        ),
        acquisition_end=parse_aware_datetime(
            payload.get("acquisition_end", ""), "acquisition_end"
        ),
        instrument_mode=str(payload.get("instrument_mode", "")),
        orbit_pass=str(payload.get("orbit_pass", "")),
        relative_orbit_number=int(payload["relative_orbit_number"]),
        polarizations=tuple(str(item) for item in polarizations),
        nominal_resolution_m=int(payload["nominal_resolution_m"]),
        asset_url=str(payload.get("asset_url", "")),
        revision=revision,
    )


def associate_scene_to_event(
    scene: SentinelSceneManifest,
    *,
    event: FloodEventWindow,
    aoi_geometry: GeometryReference,
) -> dict[str, Any]:
    """Associate by time after an explicit human-reviewed spatial coverage check."""

    aoi_geometry.require_reviewed("Sentinel scene/AOI association")
    if scene.acquisition_end < event.starts_at:
        temporal_relation = "before_event"
        offset = (event.starts_at - scene.acquisition_end).total_seconds() / 3600
    elif scene.acquisition_start > event.ends_at:
        temporal_relation = "after_event"
        offset = (scene.acquisition_start - event.ends_at).total_seconds() / 3600
    else:
        temporal_relation = "overlaps_event"
        offset = 0.0
    return {
        "schema_version": 1,
        "association_id": f"{event.event_id}:{scene.scene_id}",
        "use": "retrospective_validation_only",
        "scene_id": scene.scene_id,
        "scene_source_revision_sha256": scene.revision.sha256,
        "event_id": event.event_id,
        "event_evidence_revision_sha256": event.evidence_revision_sha256,
        "temporal_relation": temporal_relation,
        "absolute_offset_hours": offset,
        "aoi_geometry": aoi_geometry.as_dict(),
        "spatial_basis": (
            "reviewed analytical AOI reference; this scaffold does not compute "
            "scene intersection"
        ),
        "spatial_coverage_claim": False,
        "flood_extent_claim": False,
    }
