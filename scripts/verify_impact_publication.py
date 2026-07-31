"""Poll production until the intended ASDMA impact revision is served."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from axom_flood.asdma.publisher import (
    ImpactPublicationError,
    verify_impact_publication,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="https://assamflood.org")
    parser.add_argument(
        "--expected-pointer",
        default="data/processed/asdma-impact/impact-current.json",
    )
    parser.add_argument("--attempts", type=int, default=20)
    parser.add_argument("--interval", type=float, default=15)
    args = parser.parse_args()

    expected = json.loads(Path(args.expected_pointer).read_text())
    last_error: Exception | None = None
    for attempt in range(1, args.attempts + 1):
        try:
            result = verify_impact_publication(
                base_url=args.base_url,
                expected_pointer=expected,
            )
            print(json.dumps(result, indent=2, sort_keys=True))
            return
        except (ImpactPublicationError, OSError, ValueError) as exc:
            last_error = exc
            if attempt < args.attempts:
                time.sleep(args.interval)
    raise SystemExit(f"production impact verification failed: {last_error}")


if __name__ == "__main__":
    main()
