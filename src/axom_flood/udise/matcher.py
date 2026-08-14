"""District-blocked fuzzy matching of camp names to UDISE schools."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from rapidfuzz.fuzz import token_set_ratio

EXPANSIONS = {
    "lp": "lower primary",
    "lps": "lower primary school",
    "me": "middle english",
    "mes": "middle english school",
    "hs": "high school",
    "hss": "higher secondary school",
    "ghs": "government high school",
    "mv": "middle vernacular",
}
DISTRICT_ALIASES = {
    "kamrup metropolitan": {"kamrup metropolitan", "kamrup metro", "kamrup (m)"},
    "south salmara-mankachar": {"south salmara mancachar", "south salmara-mankachar"},
    "sribhumi": {"sribhumi", "karimganj"},
}


def normalize_name(value: str) -> str:
    tokens = re.findall(r"[a-z0-9]+", value.casefold().replace(".", ""))
    expanded: list[str] = []
    for token in tokens:
        expanded.extend(EXPANSIONS.get(token, token).split())
    return " ".join(expanded)


def _district_keys(value: str) -> set[str]:
    normalized = normalize_name(value)
    aliases = DISTRICT_ALIASES.get(value.casefold(), {value.casefold()})
    return {normalize_name(alias) for alias in aliases} | {normalized}


def _load_schools(path: Path) -> dict[str, list[dict[str, str]]]:
    by_district: dict[str, list[dict[str, str]]] = defaultdict(list)
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            row["_normalized_name"] = normalize_name(row["school_name"])
            row["_normalized_village"] = normalize_name(row["village"])
            by_district[normalize_name(row["district"])].append(row)
    return by_district


def _write_pointer(path: Path, *, digest: str, stable: dict[str, Any]) -> None:
    """Say which camp-match artifact is live, in a file rather than an mtime.

    Every run of this matcher leaves another content-addressed artifact behind,
    and nothing deletes the old ones. The bundle build used to take the newest
    modification time, which is right on a working copy and wrong on the fresh
    clone Cloud Run makes every run: `git checkout` stamps every file at once, so
    "newest" collapses to whichever hash the filesystem happens to hand back
    first. The two-hourly CWC job never re-runs this matcher, so it was picking
    among seven camp lists by luck.

    They all held the same 150 camps, so nothing was ever wrong on the site. The
    rainfall zone table hit the identical bug and it was not harmless there --
    a clean clone silently chose an 82-circle table over the 101-circle one. This
    is the same repair, in the same shape: mtime is fine for "the file this run
    just wrote", wrong for "the committed artifact chosen among several".
    """

    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "record": "camp_match_pointer",
                "revision_id": digest,
                "matches_url": f"data/processed/camp-matches/{digest}.json",
                "camp_source_artifact": stable["camp_source_artifact"],
                "school_source_artifact": stable["school_source_artifact"],
                "totals": {
                    "camps": stable["camp_count"],
                    "high_confidence": stable["high_confidence"],
                    "medium_confidence": stable["medium_confidence"],
                    "unverified": stable["unverified"],
                },
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def match_camps_to_schools(
    *,
    camps_path: Path,
    schools_path: Path,
    data_dir: Path,
) -> dict[str, Any]:
    camp_document = json.loads(camps_path.read_text())
    schools = _load_schools(schools_path)
    matched: list[dict[str, Any]] = []
    review: list[dict[str, Any]] = []

    for camp in camp_document["camps"]:
        candidates: list[dict[str, str]] = []
        for key in _district_keys(camp["district"]):
            candidates.extend(schools.get(key, []))
        normalized_camp = normalize_name(camp["name_raw"])
        school_like = any(
            token in normalized_camp
            for token in ("school", "primary", "secondary", "middle english", "college")
        )
        scored: list[tuple[float, bool, dict[str, str]]] = []
        if school_like:
            normalized_village = normalize_name(camp.get("village") or "")
            for school in candidates:
                score = float(token_set_ratio(normalized_camp, school["_normalized_name"]))
                village_match = bool(
                    normalized_village
                    and school["_normalized_village"]
                    and token_set_ratio(normalized_village, school["_normalized_village"]) >= 90
                )
                scored.append((score + (5 if village_match else 0), village_match, school))
        scored.sort(key=lambda item: item[0], reverse=True)
        best = scored[0] if scored else None
        ambiguous = bool(best and len(scored) > 1 and best[0] - scored[1][0] <= 5)
        confidence = "unverified"
        if best and not ambiguous:
            raw_score = best[0] - (5 if best[1] else 0)
            if raw_score >= 92 and best[1]:
                confidence = "high"
            elif raw_score >= 80:
                confidence = "medium"
        school = best[2] if best else None
        record = {
            **camp,
            "name_normalized": normalized_camp,
            "udise_match": (
                {
                    "udise_code": school["udise_code"],
                    "school_name": school["school_name"],
                    "village": school["village"],
                    "coordinates": (
                        [float(school["longitude"]), float(school["latitude"])]
                        if school["longitude"] and school["latitude"]
                        else None
                    ),
                    "score": round(best[0] - (5 if best[1] else 0), 2),
                    "village_match": best[1],
                    "ambiguous": ambiguous,
                }
                if best and school
                else None
            ),
            "udise_match_confidence": confidence,
        }
        if record["coordinates"] is None and school and confidence in {"high", "medium"}:
            record["coordinates"] = record["udise_match"]["coordinates"]
            record["geocode_confidence"] = confidence
        matched.append(record)
        if confidence in {"medium", "unverified"}:
            review.append(
                {
                    "schema_version": 1,
                    "queue_type": "udise_match_review",
                    "district": camp["district"],
                    "revenue_circle": camp["revenue_circle"],
                    "camp_name": camp["name_raw"],
                    "confidence": confidence,
                    "candidate": record["udise_match"],
                }
            )

    stable = {
        "schema_version": 1,
        "matcher_version": 1,
        "camp_source_artifact": camp_document.get("artifact_id") or camps_path.stem,
        "school_source_artifact": schools_path.stem,
        "camp_count": len(matched),
        "high_confidence": sum(x["udise_match_confidence"] == "high" for x in matched),
        "medium_confidence": sum(x["udise_match_confidence"] == "medium" for x in matched),
        "unverified": sum(x["udise_match_confidence"] == "unverified" for x in matched),
        "camps": matched,
    }
    digest = hashlib.sha256(
        (json.dumps(stable, ensure_ascii=False, sort_keys=True) + "\n").encode()
    ).hexdigest()
    output_dir = data_dir / "processed" / "camp-matches"
    review_dir = data_dir / "review" / "camp-matches"
    output_dir.mkdir(parents=True, exist_ok=True)
    review_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{digest}.json"
    review_path = review_dir / f"{digest}.json"
    output_path.write_text(json.dumps(stable, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    _write_pointer(output_dir / "current.json", digest=digest, stable=stable)
    review_path.write_text(
        json.dumps(
            {"schema_version": 1, "artifact_id": digest, "items": review},
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    return {
        "artifact_id": digest,
        "camp_count": len(matched),
        "high_confidence": stable["high_confidence"],
        "medium_confidence": stable["medium_confidence"],
        "unverified": stable["unverified"],
        "json": str(output_path),
        "review_queue": str(review_path),
    }
