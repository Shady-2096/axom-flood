"""No-write connectivity probe for the official CWC and ASDMA sources."""

from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request
from typing import Any

CWC_BASE_URL = "https://ffs.india-water.gov.in"
ASDMA_FORM_URL = "https://sdrf.assam.gov.in/dfr/download?type=flood"
USER_AGENT = "AxomFloodCloudRunProbe/0.1"
CSRF_TOKEN = re.compile(rb'name="_token"\s+value="[^"]+"')


def _eq(field: str, value: str) -> dict[str, Any]:
    return {
        "expression": {
            "valueIsRelationField": False,
            "fieldName": field,
            "operator": "eq",
            "value": value,
        }
    }


def _request(url: str, *, accept: str, timeout: float = 45) -> tuple[bytes, int, float]:
    request = urllib.request.Request(
        url,
        headers={"Accept": accept, "User-Agent": USER_AGENT},
    )
    started = time.monotonic()
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read()
        return body, response.status, time.monotonic() - started


def probe_cwc() -> dict[str, Any]:
    specification = {
        "where": _eq("id.datatypeCode", "HHS"),
        "and": _eq("stationCode.floodForecastStaticStationCode.type", "Level"),
    }
    query = urllib.parse.urlencode(
        {"specification": json.dumps(specification, separators=(",", ":"))}
    )
    url = f"{CWC_BASE_URL}/iam/api/new-entry-data-aggregate/specification/?{query}"
    body, status, elapsed = _request(url, accept="application/json")
    rows = json.loads(body)
    if not isinstance(rows, list) or not rows:
        raise ValueError("CWC latest-level endpoint returned no rows")
    kampur = next(
        (row for row in rows if row.get("stationCode") == "033-UBDDIB"),
        None,
    )
    return {
        "ok": True,
        "http_status": status,
        "elapsed_seconds": round(elapsed, 3),
        "row_count": len(rows),
        "kampur_latest_at": kampur.get("latestDataTime") if kampur else None,
        "kampur_latest_level_m": kampur.get("latestDataValue") if kampur else None,
    }


def probe_asdma() -> dict[str, Any]:
    body, status, elapsed = _request(ASDMA_FORM_URL, accept="text/html")
    if not CSRF_TOKEN.search(body):
        raise ValueError("ASDMA form returned without a CSRF token")
    return {
        "ok": True,
        "http_status": status,
        "elapsed_seconds": round(elapsed, 3),
        "response_bytes": len(body),
        "csrf_token_present": True,
    }


def main() -> int:
    results: dict[str, Any] = {"schema_version": 1}
    failed = False
    for name, probe in (("cwc", probe_cwc), ("asdma", probe_asdma)):
        try:
            results[name] = probe()
        except Exception as exc:
            failed = True
            results[name] = {
                "ok": False,
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
    print(json.dumps(results, indent=2, sort_keys=True))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
