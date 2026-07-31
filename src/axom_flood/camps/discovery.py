"""Bounded crawler for relief-camp documents on Assam district sites."""

from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

USER_AGENT = "AxomFloodData/0.1 (+public-interest flood data pipeline)"
PROBE_PATHS = (
    "/document-search",
    "/departments-list",
    "/document/reports",
    "/document/notifications",
    "/departments/revenue-and-disaster-management",
)
KEYWORDS = re.compile(
    r"\b(relief\s*camps?|pre[\s-]*identified\s+relief|flood\s+contingency|"
    r"district\s+disaster\s+management\s+plan|ddmp)\b",
    re.IGNORECASE,
)


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[dict[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            self._href = dict(attrs).get("href")
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._href is not None:
            self.links.append({"href": self._href, "text": " ".join("".join(self._text).split())})
            self._href = None
            self._text = []


def load_district_registry(path: Path) -> dict[str, Any]:
    registry = json.loads(path.read_text())
    if len(registry.get("districts", [])) != 35:
        raise ValueError("district registry must contain exactly 35 districts")
    return registry


def _links(html: str, base_url: str) -> list[dict[str, str]]:
    parser = _LinkParser()
    parser.feed(html)
    return [
        {"url": urljoin(base_url, item["href"]), "title": item["text"]}
        for item in parser.links
        if item["href"]
    ]


def _allowed(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host.endswith(".assam.gov.in") or host == "assam.gov.in"


def _document_type(title: str) -> str:
    if re.search(r"relief\s*camps?|pre[\s-]*identified", title, re.IGNORECASE):
        return "dedicated_camp_list"
    return "contingency_plan"


def discover_district_sources(
    registry: dict[str, Any],
    *,
    client: httpx.Client,
) -> dict[str, Any]:
    def discover_one(district: dict[str, Any]) -> dict[str, Any]:
        slugs = [district["slug"], *district.get("alternate_slugs", [])]
        candidates: dict[str, dict[str, str]] = {
            seed["url"]: dict(seed) for seed in district.get("seed_documents", [])
        }
        probes: list[dict[str, Any]] = []
        candidate_pages: list[dict[str, str]] = []
        for slug in slugs:
            base = f"https://{slug}.assam.gov.in"
            for path in PROBE_PATHS:
                url = base + path
                try:
                    response = client.get(url)
                    response.raise_for_status()
                    probes.append({"url": url, "status": response.status_code, "ok": True})
                    for link in _links(response.text, str(response.url)):
                        if KEYWORDS.search(link["title"]) and _allowed(link["url"]):
                            candidate_pages.append(link)
                except httpx.HTTPError as exc:
                    probes.append({"url": url, "ok": False, "error": type(exc).__name__})

        for candidate in candidate_pages:
            url = candidate["url"]
            if url.lower().split("?", 1)[0].endswith(".pdf"):
                candidates[url] = {
                    **candidate,
                    "document_type": _document_type(candidate["title"]),
                }
                continue
            try:
                response = client.get(url)
                response.raise_for_status()
                for link in _links(response.text, str(response.url)):
                    if link["url"].lower().split("?", 1)[0].endswith(".pdf") and _allowed(
                        link["url"]
                    ):
                        candidates[link["url"]] = {
                            "title": candidate["title"] or link["title"],
                            "url": link["url"],
                            "document_type": _document_type(
                                candidate["title"] or link["title"]
                            ),
                        }
            except httpx.HTTPError:
                continue

        return {
            "district": district["name"],
            "slug": district["slug"],
            "probes": probes,
            "documents": sorted(candidates.values(), key=lambda item: item["url"]),
            "discovery_status": "found" if candidates else "no_candidate_found",
        }

    with ThreadPoolExecutor(max_workers=10) as executor:
        districts = list(executor.map(discover_one, registry["districts"]))
    return {"schema_version": 1, "district_count": len(districts), "districts": districts}
