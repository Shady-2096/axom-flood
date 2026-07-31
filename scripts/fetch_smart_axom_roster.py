"""Snapshot ASDMA's SMART AXOM gauge roster as a station-to-circle crosswalk.

SMART AXOM's water-level page is a mirror of CWC FFS: every station it publishes
is already in FFS, and FFS is roughly an hour fresher, so this is deliberately
*not* a live source. Levels are read from FFS as before.

What the mirror adds is editorial. It names the subset of FFS stations ASDMA
itself treats as Assam-relevant, and it carries `rc_name`, the revenue circle a
gauge warns for. FFS resolves a station only as far as a tahsil, which is not the
same administrative unit, so the circle cannot be derived from FFS alone.

The snapshot is therefore reference data, refreshed rarely and by hand. Levels
present in the response are recorded only as provenance for the reading that
accompanied each mapping; nothing downstream should treat them as current.

The endpoint authenticates with a fixed identifier encrypted under a key
hardcoded in the site's own JavaScript bundle. Both constants are shipped to
every visitor, so this is obfuscation rather than a secret, and it is reproduced
here rather than stored as a credential.
"""

from __future__ import annotations

import argparse
import base64
import json
import ssl
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from jsonschema import Draft202012Validator, FormatChecker

from axom_flood.cwc.client import IST

ROOT = Path(__file__).resolve().parents[1]

ENDPOINT = "https://smartaxom.nesdr.gov.in/api_v2/dataCWC"
DEFAULT_OUTPUT = ROOT / "config" / "smart-axom-gauge-circles.json"
SCHEMA_NAME = "smart-axom-gauge-circles.schema.json"

# Read from the `dataCWC` caller in the site's JS chunk on 2026-07-30. If the
# request starts returning `Error 401 ! Unauthorized Access`, these rotated.
_KEY_ID = "tDqR0XLgej9c0QuYabX69GR4cLl2H1eq"
_AES_KEY = b"quvaFPLNdcpHqUgmrE71JI6QoSeq4dAZ"
_AES_IV = b"5034195220579759"


def _encrypted_key() -> bytes:
    """Reproduce the site's `p(JSON.stringify({keyId}))`: AES-256-CBC, base64."""
    payload = json.dumps({"keyId": _KEY_ID}, separators=(",", ":")).encode()
    padding = 16 - len(payload) % 16
    padded = payload + bytes([padding]) * padding
    encryptor = Cipher(algorithms.AES(_AES_KEY), modes.CBC(_AES_IV)).encryptor()
    return base64.b64encode(encryptor.update(padded) + encryptor.finalize())


def _tls_context() -> Any:
    """Verify against the operating system's trust store.

    The host serves a malformed chain: it repeats an intermediate and routes up
    through Comodo's `AAA Certificate Services`, which certifi no longer carries.
    OpenSSL follows that branch and rejects the connection as containing a
    self-signed certificate, even though certifi does hold the emSign root the
    chain is anchored on. `curl` and the OS verifier both accept it.

    Verification is never disabled: without `truststore` the caller is told to
    refresh from a saved response instead.
    """
    try:
        import truststore
    except ModuleNotFoundError:
        return True
    return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)


def fetch_rows(*, timeout: float = 60.0) -> list[dict[str, Any]]:
    try:
        response = httpx.post(
            ENDPOINT,
            files={"key": (None, _encrypted_key())},
            timeout=timeout,
            headers={"User-Agent": "AxomFloodData/0.1"},
            verify=_tls_context(),
        )
    except httpx.ConnectError as exc:
        if "CERTIFICATE_VERIFY_FAILED" not in str(exc):
            raise
        raise RuntimeError(
            "TLS verification failed against certifi's bundle. Install the `dev` "
            "extra for `truststore`, or save the response with curl and rebuild "
            "with --input."
        ) from exc
    response.raise_for_status()
    payload = response.json()
    if not payload.get("success"):
        raise RuntimeError(f"SMART AXOM refused the request: {payload.get('message')}")
    rows = payload.get("data")
    if not isinstance(rows, list) or not rows:
        raise ValueError("SMART AXOM returned no station rows")
    return rows


def _clean(value: Any) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def build_document(rows: list[dict[str, Any]], *, fetched_at: datetime) -> dict[str, Any]:
    stations = []
    for row in rows:
        code = _clean(row.get("stationcode"))
        if code is None:
            continue
        stations.append(
            {
                "cwc_station_code": code,
                "site_name": _clean(row.get("name")) or code,
                "revenue_circle_source_name": _clean(row.get("rc_name")),
                "district_source_name": _clean(row.get("district_n")),
                "river_source_name": _clean(row.get("river_name")),
                "basin_source_name": _clean(row.get("basin_name")),
                "station_type": _clean(row.get("type")),
                # Thresholds are recorded for cross-checking FFS, never to
                # override it: FFS publishes the same values and is the origin.
                "danger_level_m": _number(row.get("danger_flow_level")),
                "warning_level_m": _number(row.get("warning_flow_level")),
                "highest_flood_level_m": _number(row.get("high_flow_level")),
                "observed_level_m": _number(row.get("current_flow_level")),
                "observed_at": _clean(row.get("last_update")),
            }
        )
    stations.sort(key=lambda item: item["cwc_station_code"])
    return {
        "schema_version": 1,
        "source": "ASDMA SMART AXOM water level information",
        "source_url": "https://smartaxom.nesdr.gov.in/analytics/flood/waterlevelinfo",
        "source_endpoint": ENDPOINT,
        "fetched_at": fetched_at.isoformat(),
        "usage": (
            "Reference only. Every station here is also in CWC FFS, which is "
            "fresher and remains the source of observed levels. This snapshot "
            "supplies the revenue-circle name FFS does not publish."
        ),
        "station_count": len(stations),
        "stations": stations,
    }


def _validate(document: dict[str, Any]) -> None:
    schema = json.loads((ROOT / "schemas" / SCHEMA_NAME).read_text())
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(document)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--input",
        type=Path,
        help="rebuild from a saved raw response instead of calling the endpoint",
    )
    args = parser.parse_args(argv)

    rows = json.loads(args.input.read_text())["data"] if args.input else fetch_rows()

    document = build_document(rows, fetched_at=datetime.now(IST))
    _validate(document)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n")

    with_circle = sum(1 for s in document["stations"] if s["revenue_circle_source_name"])
    print(
        json.dumps(
            {
                "output": str(args.output),
                "station_count": document["station_count"],
                "stations_with_revenue_circle": with_circle,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
