"""Fetch and cache multi-year hourly gauge history from CWC FFS.

One request per station, cached permanently under gitignored `data/cache/`, so
this is never asked of a government server twice. The cached bodies are large
(roughly 80,000 rows per station over seven years) and are deliberately not
committed; the small derived reference table is the committed artifact.

Usage:
    uv run python scripts/fetch_gauge_history.py --since 2019-01-01
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from axom_flood.cwc.client import FfsClient
from axom_flood.cwc.pipeline import IST, _select_stations, load_district_lookup


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--since", default="2019-01-01")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--max-workers", type=int, default=3)
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    since = datetime.fromisoformat(args.since).replace(tzinfo=IST)
    cache = data_dir / "cache" / "cwc-history"
    cache.mkdir(parents=True, exist_ok=True)

    with FfsClient(timeout=300) as client:
        reference = client.fetch_reference(
            cache_dir=data_dir / "cache" / "cwc-reference"
        )
        stations = _select_stations(
            reference,
            states=("Assam",),
            upstream_states=("Arunachal Pradesh",),
            district_lookup=load_district_lookup(),
        )
        pending = [
            code for code in sorted(stations) if not (cache / f"{code}.json").exists()
        ]
        print(f"{len(stations)} stations selected, {len(pending)} to fetch", flush=True)

        for index, code in enumerate(pending, start=1):
            try:
                rows = client.fetch_station_series(code, since=since)
            except Exception as exc:  # noqa: BLE001 - one station must not stop the run
                print(f"  [{index}/{len(pending)}] {code} FAILED {type(exc).__name__}", flush=True)
                continue
            (cache / f"{code}.json").write_text(json.dumps(rows))
            years = sorted({row["id"]["dataTime"][:4] for row in rows})
            print(
                f"  [{index}/{len(pending)}] {code} {len(rows)} level rows "
                f"{years[0] if years else '-'}..{years[-1] if years else '-'}",
                flush=True,
            )

    cached = sorted(cache.glob("*.json"))
    print(f"cached history for {len(cached)} stations in {cache}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
