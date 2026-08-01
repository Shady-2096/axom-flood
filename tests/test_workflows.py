from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_daily_pipeline_publishes_and_stages_the_runtime_bundle() -> None:
    workflow = (ROOT / ".github/workflows/phase0-daily.yml").read_text()

    assert "uv run python scripts/build_pwa_bundle.py" in workflow
    assert "git add config data static/data" in workflow
    assert "steps.pwa_bundle.outcome == 'success'" in workflow
    assert 'test "$PWA_BUNDLE_OUTCOME" = success' in workflow


def test_daily_pipeline_remeasures_gauge_distances_before_it_builds_the_bundle() -> None:
    """A CWC ingest can change the station list the distances are measured against.

    If the audit does not run in between, the bundle publishes distances taken
    from stations that may have moved, been revised, or been retired — and the
    committed registry quietly stops matching the published data.
    """
    workflow = (ROOT / ".github/workflows/phase0-daily.yml").read_text()
    audit = "uv run python scripts/audit_gauge_mappings.py --write"

    assert audit in workflow
    assert workflow.index("axom-flood cwc") < workflow.index(audit)
    assert workflow.index(audit) < workflow.index("scripts/build_pwa_bundle.py")
    # The registry the audit writes back to lives in config/, so a commit step
    # that only stages data/ would throw the audit's work away every run.
    assert "git add config data static/data" in workflow
    assert "steps.gauge_audit.outcome == 'success'" in workflow
    assert 'test "$GAUGE_AUDIT_OUTCOME" = success' in workflow


def test_ci_validates_reviewed_gauge_decisions() -> None:
    """A bad decision must fail the push, not the next unattended run.

    Reviewed decisions are the one path that can promote a gauge mapping, and
    they land straight in a reader's bulletin. Catching a decision that names a
    dead gauge only when the nightly job runs means it has already shipped.
    """
    workflow = (ROOT / ".github/workflows/phase1-ci.yml").read_text()

    assert "uv run python scripts/apply_gauge_decisions.py --check" in workflow
