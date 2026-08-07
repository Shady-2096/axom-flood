import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location(
    "check_pwa_budget", ROOT / "scripts/check_pwa_budget.py"
)
assert SPEC and SPEC.loader
budget = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(budget)


def test_first_visit_budget_excludes_unreferenced_chunks_and_data(
    tmp_path: Path, monkeypatch
) -> None:
    build = tmp_path / "build"
    (build / "home").mkdir(parents=True)
    (build / "_app/immutable/chunks").mkdir(parents=True)
    (build / "data").mkdir()
    (build / "fonts").mkdir()
    (build / "home/index.html").write_text(
        '<script src="/_app/immutable/chunks/shell.js"></script>'
        '<link href="/styles.css">',
        encoding="utf-8",
    )
    (build / "index.html").write_text(
        '<script src="/_app/immutable/chunks/landing.js"></script>',
        encoding="utf-8",
    )
    (build / "_app/immutable/chunks/shell.js").write_text("shell", encoding="utf-8")
    landing = build / "_app/immutable/chunks/landing.js"
    landing.write_text("landing", encoding="utf-8")
    lazy = build / "_app/immutable/chunks/lazy.js"
    lazy.write_text("lazy", encoding="utf-8")
    (build / "styles.css").write_text("style", encoding="utf-8")
    (build / "fonts/app.woff2").write_bytes(b"font")
    (build / "data/current.json").write_text("data", encoding="utf-8")
    monkeypatch.setattr(budget, "BUILD", build)

    included = budget.first_visit_files()

    assert build / "home/index.html" in included
    assert build / "index.html" not in included
    assert build / "_app/immutable/chunks/shell.js" in included
    assert landing not in included
    assert build / "styles.css" in included
    assert build / "fonts/app.woff2" in included
    assert build / "data/current.json" not in included
    assert budget.lazy_chunk_files(included) == {landing, lazy}


def _minimal_build(tmp_path: Path, lazy_bytes: int) -> Path:
    """A build with a first visit well under its limit and a lazy chunk we choose."""
    build = tmp_path / "build"
    (build / "home").mkdir(parents=True)
    (build / "_app/immutable/chunks").mkdir(parents=True)
    (build / "home/index.html").write_text(
        '<script src="/_app/immutable/chunks/shell.js"></script>', encoding="utf-8"
    )
    (build / "_app/immutable/chunks/shell.js").write_text("shell", encoding="utf-8")
    (build / "_app/immutable/chunks/maplibre.js").write_bytes(b"x" * lazy_bytes)
    return build


def test_an_oversized_lazy_map_bundle_fails_the_build(tmp_path: Path, monkeypatch) -> None:
    """The number used to be printed and ignored. It is a gate now.

    Detailed mode has no download budget, but it still has to start on a phone
    several years old, and a lazy chunk is exactly where a second heavy library
    can arrive without anything about the first visit noticing.
    """

    build = _minimal_build(tmp_path, budget.LAZY_LIMIT + 1)
    monkeypatch.setattr(budget, "BUILD", build)

    with pytest.raises(SystemExit) as caught:
        budget.main()

    message = str(caught.value)
    assert "device ceiling" in message
    # The total alone cannot answer "what got bigger", so the biggest files are
    # named in the failure.
    assert "maplibre.js" in message


def test_a_lazy_bundle_under_the_ceiling_passes(tmp_path: Path, monkeypatch) -> None:
    build = _minimal_build(tmp_path, budget.LAZY_LIMIT - 1)
    monkeypatch.setattr(budget, "BUILD", build)

    budget.main()
