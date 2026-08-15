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


def test_the_publication_watchdog_actually_runs_on_a_schedule() -> None:
    """A watchdog nobody triggers is a watchdog that never barks.

    The rainfall layer stopped publishing on 2026-08-07 and was still dark eight
    days later. The check that would have said so existed the whole time; it was
    a command somebody had to remember to type. So the schedule is the load-
    bearing part of this file, not the script it calls.
    """
    workflow = (ROOT / ".github/workflows/publication-watchdog.yml").read_text()

    assert "schedule:" in workflow
    assert "cron:" in workflow
    assert "node scripts/check_publication_freshness.mjs" in workflow
    # It has to be able to say something, not just fail a run nobody watches.
    assert "issues: write" in workflow
    assert "issues.create" in workflow


def test_the_watchdog_reads_a_current_checkout() -> None:
    """`static/data` is what the site downloads, so it only describes what a
    reader sees when the checkout is the published one. Against a stale clone the
    check reports darkness that is not there — which would train everyone to
    ignore it, the one failure a watchdog cannot survive."""
    workflow = (ROOT / ".github/workflows/publication-watchdog.yml").read_text()

    assert "actions/checkout@v4" in workflow
    assert "ref: main" in workflow


def test_the_freshness_check_stays_out_of_the_ci_chain() -> None:
    """An upstream agency having a quiet week must not fail a stylesheet change.

    ASDMA is blocked from cloud hosts and runs off one Mac; gaps are expected and
    documented. Wiring this into CI would make somebody else's outage look like
    our broken build, and the fix would be to delete the check.
    """
    ci = (ROOT / ".github/workflows/phase1-ci.yml").read_text()

    assert "check_publication_freshness" not in ci
