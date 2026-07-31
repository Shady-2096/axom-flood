#!/usr/bin/env bash
set -euo pipefail

mode="${1:-probe}"
repository="${AXOM_GITHUB_REPOSITORY:-Shady-2096/Axom-floods}"

publish_changes() {
  local message="$1"

  # config/ is here because the gauge-distance audit writes back to
  # config/assam-localities.json. Without it the audit would recompute the
  # distances on every run, publish a bundle built from them, and then throw the
  # registry away — so the committed registry and the published bundle would
  # disagree, and the next run would do it again.
  git add config data static/data
  if git diff --cached --quiet; then
    echo "No data changes to publish."
    return
  fi

  git config user.name "axom-flood-data-bot"
  git config user.email "actions@users.noreply.github.com"
  git commit -m "$message"

  if [[ "${AXOM_PUBLISH_DRY_RUN:-0}" == "1" ]]; then
    echo "Dry run: commit created locally but not pushed."
    return
  fi

  if [[ -z "${GITHUB_DEPLOY_KEY:-}" ]]; then
    echo "GITHUB_DEPLOY_KEY is required to publish data." >&2
    exit 1
  fi

  local key_path="${job_root}/github-deploy-key"
  printf '%s\n' "$GITHUB_DEPLOY_KEY" > "$key_path"
  chmod 0600 "$key_path"
  export GIT_SSH_COMMAND="ssh -i ${key_path} -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new"
  git remote set-url origin "git@github.com:${repository}.git"
  git push origin HEAD:main
}

prepare_checkout() {
  job_root="$(mktemp -d)"
  export job_root
  trap 'rm -rf "$job_root"' EXIT

  git clone --depth 1 "https://github.com/${repository}.git" "${job_root}/repo"
  cd "${job_root}/repo"
  uv sync --locked
}

run_daily_pipeline() {
  local failed=0

  run_step() {
    local name="$1"
    shift
    echo "Running ${name}..."
    if ! "$@"; then
      echo "${name} failed." >&2
      failed=1
    fi
  }

  run_step asdma uv run axom-flood asdma latest \
    --lookback-days 3 --timeout 180 --max-attempts 3 --retry-backoff 2
  run_step camps uv run axom-flood camps --timeout 30
  run_step camp-matches uv run axom-flood udise match
  run_step nwdp-gauges uv run axom-flood gauges \
    --source \
    "https://nwdp.nwic.gov.in/dataset/6273c426-32f9-4fdf-b67f-e4e7a46d8554/resource/847f5630-f231-46c0-922d-0f2f379a5cb8/download/rwl_tel_hr_assam_999_2026_2030.csv"
  run_step cwc uv run axom-flood cwc --backfill-hours 12
  run_step smart-axom uv run axom-flood flews
  # Between the CWC ingest and the bundle build, because the ingest is what can
  # change the station list this audit measures against.
  run_step gauge-audit uv run python scripts/audit_gauge_mappings.py --write
  run_step pwa-bundle uv run python scripts/build_pwa_bundle.py

  if [[ "$failed" == "0" ]]; then
    uv run axom-flood monitor record \
      --run-id "${CLOUD_RUN_EXECUTION:-cloud-run-manual}" \
      --run-origin "${AXOM_RUN_ORIGIN:-schedule}"
  fi

  publish_changes "data: run scheduled Cloud Run pipelines"
  return "$failed"
}

case "$mode" in
  probe)
    exec python /opt/axom-cloudrun/probe.py
    ;;
  cwc)
    prepare_checkout
    uv run axom-flood cwc --backfill-hours 12
    # A CWC ingest can write a new station reference: a station moves, a
    # threshold is revised, one is added or retired. Any of those changes how far
    # each revenue circle sits from the gauge it reads from, so the audit has to
    # run again before the bundle is built from it. Otherwise the distances the
    # map and the gauge note show are measured against a station list that no
    # longer exists.
    #
    # Deliberately not fatal on this path. It is the frequent job that keeps
    # river levels flowing, and a stale distance figure is a far smaller harm
    # than an hour with no readings at all. The daily job treats the same step as
    # a real failure, and CI fails outright if the registry drifts.
    if ! uv run python scripts/audit_gauge_mappings.py --write; then
      echo "WARNING: gauge-distance audit failed; publishing readings with the previous distances." >&2
    fi
    uv run python scripts/build_pwa_bundle.py
    publish_changes "data: refresh CWC gauges from Cloud Run"
    ;;
  daily)
    prepare_checkout
    run_daily_pipeline
    ;;
  *)
    echo "Unsupported Cloud Run mode: $mode" >&2
    exit 2
    ;;
esac
