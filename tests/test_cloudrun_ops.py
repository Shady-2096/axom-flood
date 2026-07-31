from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_cloud_run_probe_is_read_only_and_checks_both_live_sources() -> None:
    probe = (ROOT / "ops/cloudrun/probe.py").read_text()

    assert "new-entry-data-aggregate/specification" in probe
    assert "033-UBDDIB" in probe
    assert "sdrf.assam.gov.in/dfr/download?type=flood" in probe
    assert "csrf_token_present" in probe
    assert "urllib.request.urlopen" in probe
    assert "write_text(" not in probe
    assert "write_bytes(" not in probe


def test_cloud_run_image_defaults_to_the_probe_gate() -> None:
    dockerfile = (ROOT / "ops/cloudrun/Dockerfile").read_text()
    entrypoint = (ROOT / "ops/cloudrun/run-job.sh").read_text()

    assert 'CMD ["probe"]' in dockerfile
    assert 'mode="${1:-probe}"' in entrypoint
    assert "probe)" in entrypoint


def test_cwc_job_refreshes_the_runtime_bundle_before_publishing() -> None:
    entrypoint = (ROOT / "ops/cloudrun/run-job.sh").read_text()
    cwc_mode = entrypoint.split("  cwc)", 1)[1].split("    ;;", 1)[0]

    assert "prepare_checkout" in cwc_mode
    assert "uv run axom-flood cwc --backfill-hours 12" in cwc_mode
    assert "uv run python scripts/build_pwa_bundle.py" in cwc_mode
    assert 'publish_changes "data: refresh CWC gauges from Cloud Run"' in cwc_mode


def test_every_publishing_job_remeasures_gauge_distances_after_a_cwc_ingest() -> None:
    """The ingest is what can change the station list the distances are measured
    against, so the audit belongs between it and the bundle build.

    On the frequent CWC path the audit is deliberately non-fatal: it is the job
    that keeps river levels flowing, and a stale distance figure is a much smaller
    harm than an hour with no readings. The daily job treats it as a real step.
    """
    entrypoint = (ROOT / "ops/cloudrun/run-job.sh").read_text()
    audit = "scripts/audit_gauge_mappings.py --write"

    cwc_mode = entrypoint.split("  cwc)", 1)[1].split("    ;;", 1)[0]
    assert audit in cwc_mode
    assert cwc_mode.index("axom-flood cwc") < cwc_mode.index(audit)
    assert cwc_mode.index(audit) < cwc_mode.index("scripts/build_pwa_bundle.py")
    assert "WARNING: gauge-distance audit failed" in cwc_mode

    daily = entrypoint.split("run_daily_pipeline() {", 1)[1].split("\n}", 1)[0]
    assert f"run_step gauge-audit uv run python {audit}" in daily
    assert daily.index("run_step cwc") < daily.index("run_step gauge-audit")
    assert daily.index("run_step gauge-audit") < daily.index("run_step pwa-bundle")

    # The audit writes back to config/assam-localities.json. Staging only data/
    # would discard it every run and leave the registry fighting the bundle.
    assert "git add config data static/data" in entrypoint


def test_daily_job_records_only_complete_runs_but_always_publishes_evidence() -> None:
    entrypoint = (ROOT / "ops/cloudrun/run-job.sh").read_text()

    assert 'if [[ "$failed" == "0" ]]' in entrypoint
    assert "--run-origin" in entrypoint
    assert 'publish_changes "data: run scheduled Cloud Run pipelines"' in entrypoint
    assert "return \"$failed\"" in entrypoint


def test_publisher_uses_a_write_deploy_key_and_supports_local_dry_runs() -> None:
    entrypoint = (ROOT / "ops/cloudrun/run-job.sh").read_text()

    assert "GITHUB_DEPLOY_KEY is required" in entrypoint
    assert "StrictHostKeyChecking=accept-new" in entrypoint
    assert "git push origin HEAD:main" in entrypoint
    assert "AXOM_PUBLISH_DRY_RUN" in entrypoint


def test_retired_public_watchdog_is_manual_only() -> None:
    watchdog = (ROOT / ".github/workflows/phase0-watchdog.yml").read_text()

    trigger_block = watchdog.split("permissions:", 1)[0]
    assert "workflow_dispatch:" in trigger_block
    assert "schedule:" not in trigger_block
    assert "cron:" not in trigger_block
