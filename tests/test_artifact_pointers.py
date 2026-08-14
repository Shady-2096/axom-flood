"""Choosing among committed artifacts by a pointer, not by modification time.

Every Cloud Run job starts from a fresh `git clone`, and `git checkout` stamps
every file at once. A newest-modification-time pick therefore collapses to
whichever hash the filesystem hands back first — out of 202 river snapshots and
7 camp lists, silently. The rainfall zone table had the identical bug and it was
measurably wrong on a clean clone: it chose an 82-circle table over the
101-circle one.

These tests hold the repair in place. The mtime-tie cases are written to fail if
anyone puts `st_mtime` back, because the failure mode leaves no trace in the
output — a bundle built from a ten-day-old snapshot looks entirely normal.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

_spec = importlib.util.spec_from_file_location(
    "build_pwa_bundle", ROOT / "scripts" / "build_pwa_bundle.py"
)
assert _spec and _spec.loader
_bundle = importlib.util.module_from_spec(_spec)
sys.modules["build_pwa_bundle"] = _bundle
_spec.loader.exec_module(_bundle)


def _artifact(directory: Path, name: str, payload: dict) -> Path:
    path = directory / f"{name}.json"
    path.write_text(json.dumps(payload) + "\n")
    return path


def test_pointer_wins_over_the_newest_file(tmp_path: Path) -> None:
    """The pointed-at artifact is returned even when another was written later."""

    _artifact(tmp_path, "wanted", {"which": "wanted"})
    newer = _artifact(tmp_path, "newer", {"which": "newer"})
    os.utime(newer, (2_000_000_000, 2_000_000_000))
    (tmp_path / "current.json").write_text(json.dumps({"revision_id": "wanted"}))

    assert json.loads(_bundle.pointed_at(str(tmp_path)).read_text())["which"] == "wanted"


def test_pointer_decides_when_every_file_shares_a_timestamp(tmp_path: Path) -> None:
    """The fresh-clone case: identical mtimes, so mtime cannot decide anything."""

    for name in ("aaa", "bbb", "ccc"):
        path = _artifact(tmp_path, name, {"which": name})
        os.utime(path, (1_700_000_000, 1_700_000_000))
    (tmp_path / "current.json").write_text(json.dumps({"revision_id": "bbb"}))

    assert json.loads(_bundle.pointed_at(str(tmp_path)).read_text())["which"] == "bbb"


def test_a_missing_pointer_is_fatal(tmp_path: Path) -> None:
    """Never fall back to guessing. The wrong artifact publishes silently."""

    _artifact(tmp_path, "only", {"which": "only"})
    with pytest.raises(RuntimeError, match="current.json"):
        _bundle.pointed_at(str(tmp_path))


def test_a_dangling_pointer_is_fatal(tmp_path: Path) -> None:
    _artifact(tmp_path, "present", {"which": "present"})
    (tmp_path / "current.json").write_text(json.dumps({"revision_id": "absent"}))
    with pytest.raises(RuntimeError, match="not on disk"):
        _bundle.pointed_at(str(tmp_path))


@pytest.mark.parametrize(
    "directory, record",
    [
        ("data/processed/cwc", "cwc_snapshot_pointer"),
        ("data/processed/camp-matches", "camp_match_pointer"),
    ],
)
def test_the_committed_pointer_resolves(directory: str, record: str) -> None:
    """The pointers in the repository name artifacts that are actually there.

    Without this the breakage only appears on the next scheduled run, in a
    container nobody is watching.
    """

    pointer = json.loads((ROOT / directory / "current.json").read_text())
    assert pointer["record"] == record
    target = ROOT / directory / f"{pointer['revision_id']}.json"
    assert target.exists(), f"{directory}/current.json names an artifact that is gone"


def test_the_cwc_pointer_names_the_newest_snapshot() -> None:
    """A pointer left behind is worse than no pointer.

    Every river snapshot carries its own `generated_at`, so the newest is a fact
    about the data rather than about the filesystem. If the pointer disagrees,
    something wrote a snapshot without updating the pointer beside it, and the
    site would be publishing readings older than the ones it holds.
    """

    directory = ROOT / "data" / "processed" / "cwc"
    pointer = json.loads((directory / "current.json").read_text())
    newest = max(
        (path for path in directory.glob("*.json") if path.name != "current.json"),
        key=lambda path: json.loads(path.read_text())["generated_at"],
    )
    assert pointer["revision_id"] == newest.stem
    assert pointer["generated_at"] == json.loads(newest.read_text())["generated_at"]


def test_the_matcher_writes_a_pointer_the_bundle_can_read(tmp_path: Path) -> None:
    """Round trip: whatever the writer produces, the reader has to resolve."""

    from axom_flood.udise.matcher import _write_pointer

    stable = {
        "camp_source_artifact": "camps-abc",
        "school_source_artifact": "schools-def",
        "camp_count": 150,
        "high_confidence": 38,
        "medium_confidence": 24,
        "unverified": 88,
    }
    _artifact(tmp_path, "deadbeef", {"camps": []})
    _write_pointer(tmp_path / "current.json", digest="deadbeef", stable=stable)

    assert _bundle.pointed_at(str(tmp_path)).stem == "deadbeef"
    written = json.loads((tmp_path / "current.json").read_text())
    assert written["record"] == "camp_match_pointer"
    assert written["totals"]["camps"] == 150


def test_the_bundle_no_longer_picks_any_artifact_by_mtime() -> None:
    """The whole point. Written as a source check because the bug is invisible
    at runtime — the wrong snapshot builds a bundle that reads perfectly."""

    source = (ROOT / "scripts" / "build_pwa_bundle.py").read_text()
    assert "st_mtime" not in source
