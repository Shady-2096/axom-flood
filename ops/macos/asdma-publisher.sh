#!/usr/bin/env bash
set -euo pipefail

export HOME="${HOME:-/Users/astranil}"
export PATH="${HOME}/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export GIT_TERMINAL_PROMPT=0

repository="${AXOM_GITHUB_REPOSITORY:-Shady-2096/Axom-floods}"
state_dir="${HOME}/Library/Application Support/Axom Flood"
lock_dir="${state_dir}/asdma-publisher.lock"

mkdir -p "$state_dir"
if ! mkdir "$lock_dir" 2>/dev/null; then
  echo "Another ASDMA publisher is already running."
  exit 0
fi

job_root="$(mktemp -d "${TMPDIR:-/tmp}/axom-asdma.XXXXXX")"
cleanup() {
  rm -rf "$job_root"
  rmdir "$lock_dir" 2>/dev/null || true
}
trap cleanup EXIT

echo "Cloning a fresh ${repository} main checkout..."
git clone --depth 1 "https://github.com/${repository}.git" "${job_root}/repo"
cd "${job_root}/repo"

uv sync --locked
set +e
uv run axom-flood asdma latest \
  --lookback-days 3 \
  --timeout 180 \
  --max-attempts 3 \
  --retry-backoff 2
asdma_status=$?
set -e

git add data/raw/asdma data/processed/asdma data/series/asdma_flood_summary.jsonl \
  static/data
if git diff --cached --quiet; then
  echo "No new ASDMA bulletin revision to publish."
  exit "$asdma_status"
fi

git config user.name "${AXOM_GIT_AUTHOR_NAME:-Swapnanil Nath}"
git config user.email "${AXOM_GIT_AUTHOR_EMAIL:-apixsrax@gmail.com}"
git commit -m "data: refresh ASDMA bulletin from Mac"

if [[ "${AXOM_PUBLISH_DRY_RUN:-0}" == "1" ]]; then
  echo "Dry run: ASDMA commit created locally but not pushed."
  exit "$asdma_status"
fi

# CWC may publish from Cloud Run while this job is parsing the PDF. Rebase the
# ASDMA-only commit over the newest main before pushing so independent official
# sources do not race each other.
git fetch origin main
git rebase origin/main
git push origin HEAD:main

if [[ "$asdma_status" -eq 0 && -f data/processed/asdma-impact/impact-current.json ]]; then
  uv run python scripts/verify_impact_publication.py \
    --expected-pointer data/processed/asdma-impact/impact-current.json
fi

exit "$asdma_status"
