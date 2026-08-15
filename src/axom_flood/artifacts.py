"""Choosing among committed artifacts, by what the data says rather than the disk.

Every artifact this project writes is content-addressed and never overwritten, so
a directory accumulates hundreds of them and something has to decide which one is
current. Modification time is the obvious answer and it is wrong: every Cloud Run
job starts from a fresh `git clone`, and `git checkout` stamps every file at once.
"Newest" then collapses to whichever hash the filesystem happens to hand back
first -- out of 213 river snapshots, silently, with a bundle built from a ten-day
-old reading that looks entirely normal in the output.

Two rules replace it, in order of preference.

`pointed_at` reads the `current.json` a writer left beside its artifact. This is
the strongest answer because it records a decision rather than inferring one, and
it is fatal when absent: the alternative is guessing.

`newest_by_field` reads each artifact's own timestamp -- a river snapshot's
`generated_at`, a bulletin's `report_date` -- for the directories that carry no
pointer. Slower, but the ordering is a fact about the data.

Both deliberately ignore `current.json` as a candidate. It is a pointer, not an
artifact, it carries a `generated_at` of its own, and it is written last, so both
rules would otherwise select it and every caller would fail on the missing body.
"""

from __future__ import annotations

import json
from pathlib import Path

POINTER_NAME = "current.json"


def _artifacts(directory: Path, pattern: str) -> list[Path]:
    """Every artifact matching `pattern`, with the pointer itself excluded."""

    return sorted(
        path for path in directory.glob(pattern) if path.name != POINTER_NAME
    )


def pointed_at(directory: Path | str) -> Path:
    """The artifact `current.json` in `directory` names.

    A missing or dangling pointer is fatal on purpose. Falling back to a guess is
    what this function exists to remove, and a bundle built from the wrong
    artifact leaves no trace in its own output.
    """

    directory = Path(directory)
    pointer = directory / POINTER_NAME
    if not pointer.exists():
        raise RuntimeError(f"no {pointer}; rebuild the artifact to write one")
    revision = json.loads(pointer.read_text())["revision_id"]
    target = directory / f"{revision}.json"
    if not target.exists():
        raise RuntimeError(f"{pointer} names {revision}, which is not on disk")
    return target


def newest_by_field(directory: Path | str, pattern: str, field: str) -> Path:
    """The artifact whose own `field` is latest.

    For the directories that have no pointer beside them. Reading every candidate
    costs a few hundred kilobytes once per run, which is the price of an ordering
    that means the same thing on a fresh clone as it does on the machine that
    wrote the files.
    """

    directory = Path(directory)
    matches = _artifacts(directory, pattern)
    if not matches:
        raise FileNotFoundError(f"no files matching {directory / pattern}")
    # The name breaks a tie, so two artifacts carrying the same timestamp -- one
    # bulletin re-extracted under a second extractor version, say -- still resolve
    # to the same file on every machine.
    return max(matches, key=lambda path: (json.loads(path.read_text())[field], path.name))


def the_only_one(directory: Path | str, pattern: str) -> Path:
    """The single artifact matching `pattern`, or a refusal.

    For a hand-pinned reference snapshot there is no such thing as the newest one.
    A second one appearing means somebody deliberately added it, and which of the
    two to use is their decision rather than a coin toss over file timestamps.
    """

    directory = Path(directory)
    matches = _artifacts(directory, pattern)
    if not matches:
        raise FileNotFoundError(f"no files matching {directory / pattern}")
    if len(matches) > 1:
        names = ", ".join(path.name for path in matches)
        raise RuntimeError(
            f"{directory / pattern} matches {len(matches)} files and there is no "
            f"order between them; pass one explicitly. Found: {names}"
        )
    return matches[0]
