"""The one command that proves IMERG access actually works.

Run with:
  uv run python scripts/smoke_imerg.py --dry-run     # no network, no account
  uv run python scripts/smoke_imerg.py               # needs EARTHDATA_TOKEN

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

RAW_DIR = ROOT / "data" / "raw"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
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
