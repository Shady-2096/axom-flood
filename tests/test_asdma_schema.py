import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).parents[1]


def test_published_bulletin_artifacts_match_their_versioned_schema() -> None:
    schema = json.loads((ROOT / "schemas" / "asdma-bulletin.schema.json").read_text())
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    checked_versions: set[int] = set()

    for path in sorted((ROOT / "data" / "processed" / "asdma").glob("*/*-extractor-v*.json")):
        version = int(path.stem.rsplit("-extractor-v", 1)[1])
        # v6 is an immutable, superseded extraction attempt. Schema validation
        # caught its continuation-field contract defect before v7 was released.
        if version == 6:
            continue
        validator.validate(json.loads(path.read_text()))
        checked_versions.add(version)

    assert 5 in checked_versions
    assert 7 in checked_versions


def test_phase_c_impact_artifacts_match_their_versioned_schemas() -> None:
    impact_dir = ROOT / "data" / "processed" / "asdma-impact"
    contracts = [
        (
            impact_dir.glob("validation-*.json"),
            ROOT / "schemas" / "asdma-impact-validation.schema.json",
        ),
        (
            (
                path
                for path in impact_dir.glob("impact-*-validator-v*.json")
                if json.loads(path.read_text()).get("schema_version") == 2
            ),
            ROOT / "schemas" / "asdma-impact.schema.json",
        ),
        (
            [impact_dir / "impact-current.json"],
            ROOT / "schemas" / "asdma-impact-pointer.schema.json",
        ),
        (
            [impact_dir / "impact-history.json"],
            ROOT / "schemas" / "asdma-impact-history.schema.json",
        ),
        (
            [impact_dir / "impact-status.json"],
            ROOT / "schemas" / "asdma-impact-status.schema.json",
        ),
    ]
    for paths, schema_path in contracts:
        validator = Draft202012Validator(
            json.loads(schema_path.read_text()),
            format_checker=FormatChecker(),
        )
        checked = 0
        for path in paths:
            validator.validate(json.loads(path.read_text()))
            checked += 1
        assert checked > 0


def test_reviewed_season_loss_checkpoint_matches_its_schema() -> None:
    schema = json.loads(
        (ROOT / "schemas" / "asdma-season-losses.schema.json").read_text()
    )
    checkpoint = json.loads(
        (ROOT / "static" / "data" / "asdma-season-losses.json").read_text()
    )
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(checkpoint)
