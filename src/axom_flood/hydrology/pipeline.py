"""Build immutable, review-only upstream-gauge lag evidence."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from axom_flood.cwc.history import HistorySeries, load_cached_history
from axom_flood.cwc.pipeline import load_station_reference

from .lag import analyze_relationship


def _station_summary(
    code: str,
    reference: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    station = reference.get(code) or {}
    return {
        "cwc_station_code": code,
        "site_name": station.get("site_name"),
        "river": station.get("river"),
        "district": station.get("district"),
        "state": station.get("state"),
        "coordinates": station.get("coordinates"),
    }


def build_review(
    *,
    data_dir: Path,
    config_path: Path,
    now: datetime,
) -> dict[str, Any]:
    """Analyse configured hypotheses without modifying any mapping."""

    config_body = config_path.read_bytes()
    config = json.loads(config_body)
    if not isinstance(config, dict):
        raise ValueError(f"expected a JSON object: {config_path}")
    relationships = config.get("relationships")
    if not isinstance(relationships, list) or not relationships:
        raise ValueError("upstream candidate config has no relationships")
    relationship_ids = [str(candidate["relationship_id"]) for candidate in relationships]
    if len(relationship_ids) != len(set(relationship_ids)):
        raise ValueError("upstream candidate config has duplicate relationship ids")
    allowed_topology_statuses = {"candidate_unreviewed", "hypothesis_unverified"}
    for candidate in relationships:
        if candidate["upstream_station_code"] == candidate["downstream_station_code"]:
            raise ValueError(
                f"relationship uses the same station twice: {candidate['relationship_id']}"
            )
        if candidate["topology_status"] not in allowed_topology_statuses:
            raise ValueError(
                "topology must remain unreviewed in the analysis config: "
                f"{candidate['relationship_id']}"
            )
    codes = {
        str(candidate[key])
        for candidate in relationships
        for key in ("upstream_station_code", "downstream_station_code")
    }
    cache_dir = data_dir / "cache" / "cwc-history"
    histories: dict[str, HistorySeries] = {}
    for code in sorted(codes):
        path = cache_dir / f"{code}.json"
        if not path.exists():
            raise FileNotFoundError(
                f"missing cached CWC history for {code}: {path}; "
                "run scripts/fetch_gauge_history.py"
            )
        histories[code] = load_cached_history(path, station_code=code)

    reference = load_station_reference(data_dir)
    results = []
    for candidate in relationships:
        upstream_code = str(candidate["upstream_station_code"])
        downstream_code = str(candidate["downstream_station_code"])
        analysis = analyze_relationship(
            histories[upstream_code],
            histories[downstream_code],
            now=now,
        )
        passed = analysis["quality"]["passes_quality_gates"]
        results.append(
            {
                "relationship_id": candidate["relationship_id"],
                "upstream": _station_summary(upstream_code, reference),
                "downstream": _station_summary(downstream_code, reference),
                "topology": {
                    "status": candidate["topology_status"],
                    "basis": candidate["topology_basis"],
                    "review_required": True,
                    "reviewed_by": None,
                    "reviewed_at": None,
                },
                "analysis": analysis,
                "disposition": (
                    "evidence_supports_hydrology_review"
                    if passed
                    else "insufficient_or_unstable_signal"
                ),
                "automatic_use_allowed": False,
                "mapping_changed": False,
            }
        )

    histories_provenance = {
        code: histories[code].provenance() for code in sorted(histories)
    }
    return {
        "schema_version": 1,
        "generated_at": now.isoformat(),
        "review_queue": "upstream_gauge_lag_candidates",
        "review_only": True,
        "source": {
            "name": "CWC Flood Forecasting System",
            "endpoint": "/iam/api/new-entry-data/specification/",
            "datatype": "HHS reduced level in metres above mean sea level",
            "candidate_configuration": {
                "path": str(config_path),
                "sha256": hashlib.sha256(config_body).hexdigest(),
            },
            "history": histories_provenance,
        },
        "method_limitations": [
            (
                "Correlation is evidence of repeated timing, not proof that one "
                "gauge caused or uniquely predicts the other."
            ),
            (
                "Shared rainfall, tributary inflow, regulation, telemetry gaps, "
                "and changing flood-wave speed can shift or mimic a lag."
            ),
            (
                "A passing quality result still requires river-topology review "
                "and never changes a locality mapping or official severity."
            ),
        ],
        "relationship_count": len(results),
        "relationships_supporting_review": sum(
            item["disposition"] == "evidence_supports_hydrology_review"
            for item in results
        ),
        "relationships": results,
    }


def persist_review(
    document: dict[str, Any],
    *,
    output_dir: Path,
) -> dict[str, Any]:
    """Write a content-addressed artifact and a small mutable review pointer."""

    body = (
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode()
    artifact_id = hashlib.sha256(body).hexdigest()
    output_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = output_dir / f"{artifact_id}.json"
    if artifact_path.exists() and artifact_path.read_bytes() != body:
        raise RuntimeError(f"refusing to overwrite immutable artifact: {artifact_path}")
    if not artifact_path.exists():
        artifact_path.write_bytes(body)
    pointer = {
        "schema_version": 1,
        "generated_at": document["generated_at"],
        "artifact_id": artifact_id,
        "artifact_path": artifact_path.name,
        "review_only": True,
        "relationship_count": document["relationship_count"],
        "relationships_supporting_review": document[
            "relationships_supporting_review"
        ],
    }
    pointer_path = output_dir / "current.json"
    pointer_path.write_text(
        json.dumps(pointer, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )
    return {
        **pointer,
        "json": str(artifact_path),
        "pointer": str(pointer_path),
    }


__all__ = ["build_review", "persist_review"]
