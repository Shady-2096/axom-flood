"""Generate immutable, review-only upstream-gauge timing evidence.

This command is offline: it reads the raw CWC histories already cached by
``scripts/fetch_gauge_history.py``. It never edits locality mappings, gauge
snapshots, alert sentences, or official severity.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from axom_flood.cwc.client import IST
from axom_flood.hydrology.pipeline import build_review, persist_review

ROOT = Path(__file__).resolve().parents[1]


def _read_object(path: Path) -> dict[str, Any]:
    document = json.loads(path.read_text())
    if not isinstance(document, dict):
        raise ValueError(f"expected JSON object: {path}")
    return document


def _validate(document: dict[str, Any], schema_name: str) -> None:
    schema = _read_object(ROOT / "schemas" / schema_name)
    Draft202012Validator(
        schema,
        format_checker=FormatChecker(),
    ).validate(document)


def _parse_now(value: str | None) -> datetime:
    if value is None:
        return datetime.now(IST)
    parsed = datetime.fromisoformat(value)
    return parsed.replace(tzinfo=IST) if parsed.tzinfo is None else parsed.astimezone(IST)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Analyse cached CWC histories; produce review evidence only."
    )
    parser.add_argument("--data-dir", default="data")
    parser.add_argument(
        "--config",
        default="config/upstream-gauge-candidates.json",
    )
    parser.add_argument(
        "--output-dir",
        default="data/review/upstream-gauge-lags",
    )
    parser.add_argument(
        "--now",
        help="ISO timestamp used to decide whether the current monsoon is complete.",
    )
    args = parser.parse_args()

    config_path = Path(args.config)
    _validate(
        _read_object(config_path),
        "upstream-gauge-candidates.schema.json",
    )
    review = build_review(
        data_dir=Path(args.data_dir),
        config_path=config_path,
        now=_parse_now(args.now),
    )
    _validate(review, "upstream-gauge-lag-review.schema.json")
    written = persist_review(review, output_dir=Path(args.output_dir))
    pointer = _read_object(Path(written["pointer"]))
    _validate(pointer, "upstream-gauge-lag-pointer.schema.json")

    print(
        f"review artifact {written['artifact_id']} "
        f"({review['relationships_supporting_review']}/"
        f"{review['relationship_count']} support further review)"
    )
    for relationship in review["relationships"]:
        quality = relationship["analysis"]["quality"]
        print(
            f"  {relationship['relationship_id']}: "
            f"{relationship['disposition']}; "
            f"median lag={quality['recommended_lag_hours']}h; "
            f"median r={quality['median_robust_correlation']}; "
            f"auto-use=false"
        )
    print(f"wrote {written['json']}")
    print(f"updated {written['pointer']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
