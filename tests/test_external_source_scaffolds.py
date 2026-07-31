"""Contract tests for credential-gated rainfall/model/satellite/terrain sources."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from jsonschema import Draft202012Validator, FormatChecker

from axom_flood.forecasts.glofas import (
    associate_glofas_reach,
    parse_glofas_grid_forecast,
)
from axom_flood.forecasts.google_flood import (
    GoogleFloodAccessDisabled,
    GoogleFloodStatusParser,
)
from axom_flood.rainfall.imd import (
    ImdAccessRestrictedError,
    ImdClient,
    SourceDisabledError,
)
from axom_flood.rainfall.imerg import (
    IMERG_POLICIES,
    ImergRun,
    accumulate_imerg_cell,
    parse_imerg_observations,
    prepare_imerg_zonal_join,
)
from axom_flood.rainfall.provenance import (
    GeometryReference,
    GeometryReviewRequired,
    ProvenanceError,
    SourceRevision,
    write_immutable_revision,
)
from axom_flood.satellite.sentinel import (
    FloodEventWindow,
    associate_scene_to_event,
    parse_sentinel_scene_manifest,
)
from axom_flood.terrain.merit import (
    parse_merit_hand_manifest,
    preflight_merit_hand_tile,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "external_sources"
SCHEMAS = ROOT / "schemas"
FETCHED_AT = datetime(2026, 7, 29, 12, tzinfo=UTC)
REVIEWED_GEOMETRY = GeometryReference(
    geometry_id="fixture-reviewed-assam-analysis-aoi",
    sha256="a" * 64,
    review_status="reviewed",
    reviewed_at=datetime(2026, 7, 29, 10, tzinfo=UTC),
    reviewed_by="fixture-reviewer",
)
UNREVIEWED_GEOMETRY = GeometryReference(
    geometry_id="fixture-unreviewed-display-outline",
    sha256="b" * 64,
    review_status="unreviewed",
)


def fixture_bytes(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def validate(document: dict, schema_name: str) -> None:
    schema = json.loads((SCHEMAS / schema_name).read_text())
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(document)


VALID_FIXTURE_PROVENANCE = {"captured", "transcribed", "synthetic"}


def test_every_json_fixture_declares_where_it_came_from() -> None:
    """A fixture written by the same author as the parser proves nothing.

    Labelling each one makes the difference visible: `captured` and
    `transcribed` fixtures are evidence about the provider, `synthetic` ones
    are only evidence that our code is self-consistent. The GloFAS horizon bug
    passed every check precisely because code, schema, test, and fixture all
    shared one wrong assumption.
    """
    fixtures = sorted(FIXTURES.glob("*.json"))
    assert fixtures, "expected external-source fixtures to exist"
    for path in fixtures:
        metadata = json.loads(path.read_text()).get("fixture_metadata")
        assert isinstance(metadata, dict), f"{path.name} has no fixture_metadata"
        provenance = metadata.get("fixture_provenance")
        assert provenance in VALID_FIXTURE_PROVENANCE, (
            f"{path.name} must declare fixture_provenance as one of "
            f"{sorted(VALID_FIXTURE_PROVENANCE)}, got {provenance!r}"
        )
        if provenance == "synthetic":
            assert metadata.get("provenance_note"), (
                f"{path.name} is synthetic, so it must say in provenance_note "
                "what would replace it and what is still unverified"
            )


def test_source_revision_is_content_addressed_and_immutable(tmp_path: Path) -> None:
    content = b'{"fixture":true}\n'
    revision = SourceRevision.capture(
        content,
        source_id="fixture-source",
        source_url="fixture://source/revision",
        fetched_at=FETCHED_AT,
        media_type="application/json",
    )
    first = write_immutable_revision(
        content,
        directory=tmp_path,
        revision=revision,
        suffix=".json",
    )
    second = write_immutable_revision(
        content,
        directory=tmp_path,
        revision=revision,
        suffix=".json",
    )
    assert first == second
    assert first.read_bytes() == content

    first.write_bytes(b"tampered")
    with pytest.raises(ProvenanceError, match="do not match revision"):
        write_immutable_revision(
            content,
            directory=tmp_path,
            revision=revision,
            suffix=".json",
        )


def test_imerg_early_late_semantics_and_unit_safe_accumulation() -> None:
    early = parse_imerg_observations(
        fixture_bytes("imerg-early-contract.json"),
        fetched_at=FETCHED_AT,
        source_url="fixture://imerg/early",
    )
    late = parse_imerg_observations(
        fixture_bytes("imerg-late-contract.json"),
        fetched_at=FETCHED_AT,
        source_url="fixture://imerg/late",
    )

    assert IMERG_POLICIES[ImergRun.EARLY].typical_latency_hours == 4
    assert IMERG_POLICIES[ImergRun.LATE].minimum_expected_latency_hours == 12
    assert IMERG_POLICIES[ImergRun.LATE].typical_latency_hours == 14
    assert early[0].run is ImergRun.EARLY
    assert late[0].run is ImergRun.LATE

    accumulation = accumulate_imerg_cell(early)
    # 10 mm/h for 0.5 h + 20 mm/h for 0.5 h = 15 mm, not 30 mm.
    assert float(accumulation.total_mm) == 15.0
    validate(accumulation.as_dict(), "imerg-cell-accumulation.schema.json")


def test_imerg_rejects_unit_drift_overlap_and_unreviewed_zonal_geometry() -> None:
    raw = json.loads(fixture_bytes("imerg-early-contract.json"))
    raw["units"] = "mm"
    with pytest.raises(ValueError, match="units must be exactly"):
        parse_imerg_observations(
            json.dumps(raw).encode(),
            fetched_at=FETCHED_AT,
            source_url="fixture://imerg/wrong-units",
        )

    observations = parse_imerg_observations(
        fixture_bytes("imerg-early-contract.json"),
        fetched_at=FETCHED_AT,
        source_url="fixture://imerg/overlap",
    )
    overlapped = [observations[0], observations[0]]
    with pytest.raises(ValueError, match="overlap"):
        accumulate_imerg_cell(overlapped)
    gapped = replace(
        observations[1],
        interval_start=datetime(2026, 7, 1, 0, 31, tzinfo=UTC),
    )
    with pytest.raises(ValueError, match="gap"):
        accumulate_imerg_cell([observations[0], gapped])
    with pytest.raises(GeometryReviewRequired, match="IMERG zonal join"):
        prepare_imerg_zonal_join(observations, geometry=UNREVIEWED_GEOMETRY)
    request = prepare_imerg_zonal_join(observations, geometry=REVIEWED_GEOMETRY)
    assert request["aggregation_contract"] == "area_weighted; no centre-point assignment"


def test_imd_is_disabled_by_default_and_surfaces_ip_whitelist_401() -> None:
    with ImdClient() as client, pytest.raises(SourceDisabledError, match="disabled"):
        client.fetch_state_rainfall(state_id="assam", fetched_at=FETCHED_AT)

    def restricted(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            json={"error": "fixture access restricted"},
            request=request,
        )

    with (
        ImdClient(enabled=True, transport=httpx.MockTransport(restricted)) as client,
        pytest.raises(ImdAccessRestrictedError) as exc_info,
    ):
        client.fetch_state_rainfall(state_id="assam", fetched_at=FETCHED_AT)
    assert exc_info.value.reason == "ip_whitelist_required"
    assert exc_info.value.status_code == 401


def test_glofas_is_a_30_day_advisory_that_labels_its_resolution_split() -> None:
    content = fixture_bytes("glofas-30day-contract.json")
    forecast = parse_glofas_grid_forecast(
        content,
        fetched_at=FETCHED_AT,
        source_url="fixture://glofas/30-day",
    )
    document = forecast.as_advisory_document()
    validate(document, "glofas-advisory.schema.json")
    assert document["forecast_horizon_days"] == 30
    assert document["high_resolution_through_day"] == 15
    assert document["ensemble_statistic"] == "ensemble_median"
    assert document["advisory_only"] is True
    assert document["warning_authority"] is False

    # Days 1-15 come from the finer ensemble and days 16-30 from the coarser
    # extended range. Both are kept; only their labels differ.
    tiers = [value["resolution_tier"] for value in document["grid_points"][0]["values"]]
    assert tiers == [
        "medium_range",
        "medium_range",
        "extended_range",
        "extended_range",
    ]

    with pytest.raises(GeometryReviewRequired, match="GloFAS reach"):
        associate_glofas_reach(forecast, reach_geometry=UNREVIEWED_GEOMETRY)
    association = associate_glofas_reach(
        forecast,
        reach_geometry=REVIEWED_GEOMETRY,
    )
    assert "nearest-grid distance is forbidden" in association["association_rule"]

    too_long = json.loads(content)
    too_long["grid_points"][0]["values"][-1]["valid_at"] = "2026-07-31T00:00:01Z"
    with pytest.raises(ValueError, match="30-day horizon"):
        parse_glofas_grid_forecast(
            json.dumps(too_long).encode(),
            fetched_at=FETCHED_AT,
            source_url="fixture://glofas/too-long",
        )


def test_google_flood_parser_is_typed_but_live_access_stays_disabled() -> None:
    parser = GoogleFloodStatusParser()
    with pytest.raises(GoogleFloodAccessDisabled, match="waitlist approval"):
        parser.require_live_access(api_key=None)

    status = parser.parse(
        fixture_bytes("google-flood-status-contract.json"),
        fetched_at=FETCHED_AT,
        source_url="fixture://google-flood/status",
    )
    assert status.quality_verified is True
    assert status.inundation_set_ids == ("fixture-inundation-set",)
    validate(status.as_dict(), "google-flood-status.schema.json")


def test_sentinel_retrospective_association_never_claims_flood_extent() -> None:
    scene = parse_sentinel_scene_manifest(
        fixture_bytes("sentinel-s1-scene-contract.json"),
        fetched_at=FETCHED_AT,
        source_url="fixture://sentinel/scene",
    )
    event = FloodEventWindow(
        event_id="fixture-event",
        starts_at=datetime(2026, 7, 1, tzinfo=UTC),
        ends_at=datetime(2026, 7, 3, tzinfo=UTC),
        evidence_revision_sha256="c" * 64,
    )
    with pytest.raises(GeometryReviewRequired, match="Sentinel scene/AOI"):
        associate_scene_to_event(
            scene,
            event=event,
            aoi_geometry=UNREVIEWED_GEOMETRY,
        )
    association = associate_scene_to_event(
        scene,
        event=event,
        aoi_geometry=REVIEWED_GEOMETRY,
    )
    assert association["temporal_relation"] == "overlaps_event"
    assert association["spatial_coverage_claim"] is False
    assert association["flood_extent_claim"] is False
    validate(association, "sentinel-retrospective-association.schema.json")


def test_merit_existing_hand_tile_preflight_checks_bytes_and_review(tmp_path: Path) -> None:
    manifest = parse_merit_hand_manifest(
        fixture_bytes("merit-hand-manifest-contract.json"),
        fetched_at=FETCHED_AT,
        source_url="fixture://merit/manifest",
    )
    tile_bytes = bytes.fromhex((FIXTURES / "merit-hand-tile.hex").read_text().strip())
    tile_path = tmp_path / manifest.tiles[0].filename
    tile_path.write_bytes(tile_bytes)

    with pytest.raises(GeometryReviewRequired, match="MERIT HAND"):
        preflight_merit_hand_tile(
            tile_path,
            tile=manifest.tiles[0],
            manifest=manifest,
            aoi_geometry=UNREVIEWED_GEOMETRY,
        )
    preflight = preflight_merit_hand_tile(
        tile_path,
        tile=manifest.tiles[0],
        manifest=manifest,
        aoi_geometry=REVIEWED_GEOMETRY,
    )
    assert preflight["hand_source"] == "provided_hnd_band_not_locally_derived"
    assert preflight["approximate_resolution_m"] == 90
    assert "bifurcations" in preflight["topology_limitation"]
    validate(preflight, "merit-hand-preflight.schema.json")

    tile_path.write_bytes(tile_bytes + b"tampered")
    with pytest.raises(ValueError, match="byte length"):
        preflight_merit_hand_tile(
            tile_path,
            tile=manifest.tiles[0],
            manifest=manifest,
            aoi_geometry=REVIEWED_GEOMETRY,
        )


def test_external_source_registry_matches_schema_and_disables_live_access() -> None:
    registry = json.loads((ROOT / "docs" / "external-source-registry.json").read_text())
    validate(registry, "external-source-registry.schema.json")
    assert all(source["live_enabled_by_default"] is False for source in registry["sources"])
    by_id = {source["source_id"]: source for source in registry["sources"]}
    assert by_id["imd-statewise-rainfall"]["access_mode"] == "ip_whitelist_required"
    assert by_id["google-flood-status"]["access_mode"] == "approval_required"
