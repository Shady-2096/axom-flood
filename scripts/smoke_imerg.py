"""The one command that proves IMERG access actually works.

Run with:
  uv run python scripts/smoke_imerg.py --dry-run     # no network, no account
  uv run python scripts/smoke_imerg.py --describe    # what the server calls things
  uv run python scripts/smoke_imerg.py --subset      # the Assam box, the real path
  uv run python scripts/smoke_imerg.py               # one whole global granule

The one to run first is `--describe`. It asks the OPeNDAP server for its own
listing of variable names, which is the single thing this repository is guessing
about. `--subset` then exercises the path the pipeline actually uses: request the
Assam box, parse the ASCII, and refuse it if the coordinates that come back are
not the ones asked for. Plain `--run` downloads a whole global granule and only
proves the archive path and the token, which is a weaker statement.

Everything else about IMERG is tested against synthetic bytes. That proves the
refusals and the arithmetic; it cannot prove the archive path is right, the
version suffix is current, or that the token works. This can, and it is the only
thing that can. Until it has passed once, treat granule URLs as unverified.

`--dry-run` needs nothing and is safe to run today: it prints exactly what would
be requested, so the URL can be eyeballed or pasted into a browser before any
credential exists.

Set the token with:
  export EARTHDATA_TOKEN="..."      # from https://urs.earthdata.nasa.gov/

A token alone is not enough. GES DISC must also be authorised once, under
Earthdata → Applications → Authorized Apps. A 403 with a valid token almost
always means that step was skipped.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from axom_flood.rainfall.imerg import IMERG_POLICIES, ImergRun  # noqa: E402
from axom_flood.rainfall.imerg_client import (  # noqa: E402
    ImergAuthError,
    ImergClient,
    ImergCredentialsMissing,
    granule_for,
)
from axom_flood.rainfall.provenance import write_immutable_revision  # noqa: E402
from axom_flood.rainfall.subset import (  # noqa: E402
    GridBox,
    SubsetError,
    fetch_subset,
    subset_request,
)

RAW_DIR = ROOT / "data" / "raw"
ZONES_DIR = ROOT / "data" / "processed" / "rainfall-zones"


def assam_box() -> GridBox:
    """The box the real pipeline asks for: whatever the zone weights cover.

    Taken from the same artifact `build_rainfall.py` uses, so a passing smoke
    test is a statement about the box the pipeline will really request rather
    than about a rounder one written here.

    That claim was false for a week. This took the newest file in the directory,
    and the `current.json` pointer added alongside it is a file in that directory
    too -- the newest one, every time. So the smoke test read the pointer as if it
    were a zone table and died on `KeyError: 'zones'` before reaching NASA at all.
    Reading the pointer properly is both the fix and the thing the docstring
    always said this did.
    """

    pointer = ZONES_DIR / "current.json"
    if not pointer.exists():
        raise SystemExit(f"no {pointer}; run scripts/build_rainfall_zones.py first")
    revision = json.loads(pointer.read_text())["revision_id"]
    table = ZONES_DIR / f"{revision}.json"
    if not table.exists():
        raise SystemExit(f"{pointer} names {revision}, which is not on disk")
    zones = json.loads(table.read_text())
    cells = [cell["grid_cell_id"] for zone in zones["zones"] for cell in zone["cells"]]
    return GridBox.around_cells(cells, cell_degrees=zones["cell_degrees"])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--describe",
        action="store_true",
        help="print the server's own variable listing instead of downloading data",
    )
    parser.add_argument(
        "--subset",
        action="store_true",
        help="fetch the Assam box over OPeNDAP instead of the whole global granule",
    )
    parser.add_argument("--run", choices=[item.value for item in ImergRun], default="late")
    parser.add_argument(
        "--hours-ago",
        type=float,
        default=None,
        help="how far back to ask; defaults to the run's documented latency plus two hours",
    )
    parser.add_argument("--save", action="store_true", help="write the bytes under their digest")
    args = parser.parse_args()

    run = ImergRun(args.run)
    policy = IMERG_POLICIES[run]
    hours_ago = args.hours_ago
    if hours_ago is None:
        # Ask for something old enough that a miss means the path is wrong
        # rather than that the granule has simply not been published yet.
        hours_ago = policy.typical_latency_hours + 2

    now = datetime.now(UTC)
    granule = granule_for(now - timedelta(hours=hours_ago), run=run)

    print(f"run                 {run.value} ({policy.product_short_name})")
    print(f"asking for          {granule.interval_start:%Y-%m-%d %H:%M} UTC (+30 min)")
    print(f"that is             {hours_ago:.1f} hours ago")
    print(f"documented latency  {policy.typical_latency_hours} h (expectation, not fact)")
    request = subset_request(granule, assam_box())
    if args.subset or args.describe:
        print(f"box                 {request.box.as_dict()}")
        print(f"cells asked         {request.cell_count}")
        print(f"url                 {request.describe_url if args.describe else request.url}")
    else:
        print(f"url                 {granule.url}")

    if args.dry_run:
        print("\ndry run: nothing was requested.")
        return 0

    token = os.environ.get("EARTHDATA_TOKEN", "")
    with ImergClient(enabled=True, bearer_token=token) as client:
        try:
            client.check_configuration()
        except ImergCredentialsMissing as error:
            print(f"\nnot configured: {error}")
            return 2

        if args.describe:
            # The listing is the point. Whatever the server calls the
            # precipitation field and its coordinate arrays is what the subset
            # request has to spell, and reading it off the server beats
            # guessing from documentation.
            try:
                text = client.get(request.describe_url).text
            except ImergAuthError as error:
                print(f"\nrejected: {error}")
                return 3
            print(f"\n{text.strip()[:4000]}")
            print("\nPASS — the server answered. Compare the names above with")
            print("DEFAULT_VARIABLE, DEFAULT_LON_VARIABLE and DEFAULT_LAT_VARIABLE")
            print("in src/axom_flood/rainfall/subset.py.")
            return 0

        if args.subset:
            try:
                subset = fetch_subset(client, request, fetched_at=datetime.now(UTC))
            except ImergAuthError as error:
                print(f"\nrejected: {error}")
                return 3
            except SubsetError as error:
                print(f"\nrefused: {error}")
                return 4
            print(f"\nreceived            {len(subset.content):,} bytes of normalized JSON")
            print(f"cells with a rate   {len(subset.payload['observations'])}")
            print(f"cells marked empty  {len(subset.payload['missing_cell_ids'])}")
            print(f"sha256              {subset.revision.sha256}")
            if subset.observed_latency_hours is not None:
                print(f"observed latency    {subset.observed_latency_hours:.2f} h")
            print("\nPASS — the OPeNDAP path, the token, and the ASCII parse all work.")
            return 0

        try:
            download = client.fetch_granule(granule, fetched_at=datetime.now(UTC))
        except ImergAuthError as error:
            print(f"\nrejected: {error}")
            return 3

    print(f"\nreceived            {download.revision.byte_length:,} bytes")
    print(f"sha256              {download.revision.sha256}")
    print(f"etag                {download.etag or '(none)'}")
    if download.observed_latency_hours is None:
        print("observed latency    unknown — the archive sent no publication time")
    else:
        print(
            f"observed latency    {download.observed_latency_hours:.2f} h "
            f"(documented {policy.typical_latency_hours} h)"
        )

    if args.save:
        written = write_immutable_revision(
            download.content,
            directory=RAW_DIR,
            revision=download.revision,
            suffix=".hdf5",
        )
        print(f"saved               {written.relative_to(ROOT)}")

    print("\nPASS — the archive path and the token both work.")
    print(json.dumps(download.as_dict()["granule"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
