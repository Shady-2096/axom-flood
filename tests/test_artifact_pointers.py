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


def test_camp_list_and_bulletin_are_chosen_by_their_own_timestamps(tmp_path: Path) -> None:
    """Not by mtime. The daily pipeline carries on past a failed fetch, so on
    that path there is no fresh file and the pick was arbitrary."""

    from axom_flood.cli import _newest_by_field

    older = _artifact(tmp_path, "older", {"generated_at": "2026-08-01T00:00:00+05:30"})
    _artifact(tmp_path, "newer", {"generated_at": "2026-08-14T00:00:00+05:30"})
    os.utime(older, (2_000_000_000, 2_000_000_000))

    assert _newest_by_field(tmp_path, "*.json", "generated_at").stem == "newer"


def test_an_ambiguous_reference_snapshot_is_refused(tmp_path: Path) -> None:
    """The UDISE roster is a pinned 2021 mirror. A second one appearing is
    someone's deliberate choice, and which to use is theirs to make."""

    from axom_flood.cli import _the_only_one

    (tmp_path / "assam-schools-aaa.csv").write_text("x")
    assert _the_only_one(tmp_path, "assam-schools-*.csv").name == "assam-schools-aaa.csv"

    (tmp_path / "assam-schools-bbb.csv").write_text("y")
    with pytest.raises(RuntimeError, match="no order"):
        _the_only_one(tmp_path, "assam-schools-*.csv")


def test_the_cli_no_longer_picks_any_artifact_by_mtime() -> None:
    assert "st_mtime" not in (ROOT / "src" / "axom_flood" / "cli.py").read_text()


def _reference(directory: Path, name: str, stations: dict) -> None:
    (directory / name).write_text(json.dumps({"stations": stations}))


def test_a_partial_reference_snapshot_cannot_erase_what_a_fuller_one_knew(
    tmp_path: Path,
) -> None:
    """One of the three snapshots on disk is a 37-station partial fetch that
    knows no revenue circles. Under a plain dict.update it wiped 17 of them."""

    from axom_flood.cwc.pipeline import load_station_reference

    directory = tmp_path / "reference" / "cwc"
    directory.mkdir(parents=True)
    _reference(directory, "aaa.json", {"X": {"site_name": "Kampur", "revenue_circle": "Kampur"}})
    _reference(directory, "zzz.json", {"X": {"site_name": "Kampur", "revenue_circle": None}})

    assert load_station_reference(tmp_path)["X"]["revenue_circle"] == "Kampur"


def test_reference_merge_does_not_depend_on_modification_time(tmp_path: Path) -> None:
    """The fresh-clone case. Touching a file must not change the answer."""

    from axom_flood.cwc.pipeline import load_station_reference

    directory = tmp_path / "reference" / "cwc"
    directory.mkdir(parents=True)
    _reference(directory, "aaa.json", {"X": {"river": "Kopili"}, "Y": {"river": "Jia Bharali"}})
    _reference(directory, "zzz.json", {"X": {"river": None}})

    before = load_station_reference(tmp_path)
    os.utime(directory / "aaa.json", (2_000_000_000, 2_000_000_000))
    assert load_station_reference(tmp_path) == before
    assert before["X"]["river"] == "Kopili"
    assert before["Y"]["river"] == "Jia Bharali"


def test_the_real_reference_merge_agrees_on_every_field_anything_reads() -> None:
    """Consumers want coordinates, name, river, district and state. The three
    committed snapshots agree on all of them, so the merge order cannot move a
    gauge. The two fields that do depend on order are thresholds, which nothing
    reads from here — this test fails if that stops being true."""

    import itertools

    from axom_flood.cwc.pipeline import load_station_reference

    directory = ROOT / "data" / "reference" / "cwc"
    snapshots = {
        path.name: json.loads(path.read_text())["stations"]
        for path in sorted(directory.glob("*.json"))
    }
    consumed = ("coordinates", "site_name", "river", "district", "state")
    for first, second in itertools.combinations(snapshots, 2):
        for code in set(snapshots[first]) & set(snapshots[second]):
            for field in consumed:
                assert snapshots[first][code].get(field) == snapshots[second][code].get(field), (
                    f"{code}.{field} differs between reference snapshots, so the merge "
                    f"order now decides a value a caller reads"
                )
    merged = load_station_reference(ROOT / "data")
    assert sum(1 for station in merged.values() if station.get("revenue_circle")) == 52


def _osm(directory: Path, name: str, retrieved_at: str | None) -> None:
    (directory / f"{name}.json").write_text(json.dumps({"elements": []}))
    if retrieved_at is not None:
        (directory / f"{name}.metadata.json").write_text(json.dumps({"retrieved_at": retrieved_at}))


def test_osm_snapshots_are_chosen_by_when_they_were_retrieved(tmp_path: Path) -> None:
    """Which boundary snapshot wins decides which circles pass the review, and
    therefore which circles get rainfall. Two are on disk, four days apart."""

    from axom_flood.boundaries.osm import newest_snapshot

    _osm(tmp_path, "assam-boundaries-older", "2026-07-27T14:46:33Z")
    _osm(tmp_path, "assam-boundaries-newer", "2026-07-31T03:06:33Z")
    os.utime(tmp_path / "assam-boundaries-older.json", (2_000_000_000, 2_000_000_000))

    assert newest_snapshot(tmp_path, "assam-boundaries-").stem == "assam-boundaries-newer"


def test_a_snapshot_with_no_sidecar_loses_rather_than_crashing(tmp_path: Path) -> None:
    from axom_flood.boundaries.osm import newest_snapshot

    _osm(tmp_path, "assam-boundaries-undated", None)
    _osm(tmp_path, "assam-boundaries-dated", "2026-07-31T03:06:33Z")

    assert newest_snapshot(tmp_path, "assam-boundaries-").stem == "assam-boundaries-dated"


def test_the_metadata_sidecar_is_never_returned_as_the_snapshot(tmp_path: Path) -> None:
    from axom_flood.boundaries.osm import newest_snapshot

    _osm(tmp_path, "assam-boundaries-only", "2026-07-31T03:06:33Z")
    assert newest_snapshot(tmp_path, "assam-boundaries-").name == "assam-boundaries-only.json"


def test_the_imerg_smoke_test_reads_the_zone_table_not_the_pointer() -> None:
    """It globbed the zone directory for the newest file. `current.json` lives in
    that directory and is always the newest, so every run died on
    `KeyError: 'zones'` before it reached NASA."""

    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "smoke_imerg", ROOT / "scripts" / "smoke_imerg.py"
    )
    assert spec and spec.loader
    smoke = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(smoke)

    box = smoke.assam_box()
    assert 89 < box.west < box.east < 97
    assert 23 < box.south < box.north < 29


def test_the_bundle_no_longer_picks_any_artifact_by_mtime() -> None:
    """The whole point. Written as a source check because the bug is invisible
    at runtime — the wrong snapshot builds a bundle that reads perfectly."""

    source = (ROOT / "scripts" / "build_pwa_bundle.py").read_text()
    assert "st_mtime" not in source
