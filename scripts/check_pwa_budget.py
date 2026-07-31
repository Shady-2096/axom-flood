"""Check the first-visit application shell against its regression ceiling."""

from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit

BUILD = Path("build")
LIMIT = 400 * 1024
SHELL_NAMES = {"manifest.webmanifest"}
PRECACHED_ROUTE_HTML = {
    "home/index.html",
    "camps/index.html",
    "report/index.html",
    "emergency/index.html",
    "settings/index.html",
}


class AssetReferences(HTMLParser):
    """Collect browser-loadable references from a prerendered route shell."""

    def __init__(self) -> None:
        super().__init__()
        self.references: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for name, value in attrs:
            # Navigation anchors are destinations, not browser-loaded assets.
            # Route HTML that the service worker installs is seeded explicitly
            # in PRECACHED_ROUTE_HTML instead of discovered through every nav.
            if value and (name == "src" or (name == "href" and tag == "link")):
                self.references.add(value)


def build_path(reference: str, html_path: Path) -> Path | None:
    """Resolve a local HTML reference to a file under the build directory."""
    route = "/" + html_path.relative_to(BUILD).as_posix()
    resolved = urlsplit(urljoin(route, reference))
    if resolved.scheme or resolved.netloc or resolved.path.startswith("/data/"):
        return None
    relative = unquote(resolved.path).lstrip("/")
    build_root = BUILD.resolve()
    candidate = (BUILD / relative).resolve()
    if candidate.is_dir():
        candidate /= "index.html"
    try:
        candidate.relative_to(build_root)
    except ValueError:
        return None
    return BUILD / candidate.relative_to(build_root) if candidate.is_file() else None


def first_visit_files() -> set[Path]:
    """Return the prerendered shells and assets that those shells reference."""
    html_files = {
        BUILD / relative
        for relative in PRECACHED_ROUTE_HTML
        if (BUILD / relative).is_file()
    }
    included = set(html_files)
    for html_path in html_files:
        parser = AssetReferences()
        parser.feed(html_path.read_text(encoding="utf-8"))
        for reference in parser.references:
            path = build_path(reference, html_path)
            if path is not None:
                included.add(path)

    # The service worker also precaches the small static shell copied from
    # static/. Fonts are referenced from CSS rather than HTML, so include their
    # directory explicitly. report.css is intentionally route-lazy.
    included.update(path for path in (BUILD / "fonts").rglob("*") if path.is_file())
    included.update(
        path
        for path in BUILD.iterdir()
        if path.is_file()
        and (
            path.name in SHELL_NAMES
            or (path.suffix == ".css" and path.name != "report.css")
            or path.name.startswith(("icon", "favicon", "apple-touch-icon"))
        )
    )
    return included


def lazy_chunk_files(included: set[Path]) -> set[Path]:
    immutable = BUILD / "_app" / "immutable"
    if not immutable.exists():
        return set()
    return {
        path
        for path in immutable.rglob("*")
        if path.is_file() and path not in included
    }


def main() -> None:
    if not BUILD.exists():
        raise SystemExit("built PWA output not found; run npm run build")
    files = first_visit_files()
    if not files:
        raise SystemExit("built PWA output not found; run npm run build")

    size = sum(path.stat().st_size for path in files)
    lazy_size = sum(path.stat().st_size for path in lazy_chunk_files(files))
    print(f"Phase 1 first visit: {size} bytes / {LIMIT} bytes")
    print(f"Excluded lazy chunks: {lazy_size} bytes (informational only)")
    if size >= LIMIT:
        raise SystemExit("first-visit PWA exceeds 400 KiB regression alarm")


if __name__ == "__main__":
    main()
