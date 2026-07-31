import plistlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_asdma_mac_publisher_uses_a_fresh_idempotent_checkout() -> None:
    publisher = (ROOT / "ops/macos/asdma-publisher.sh").read_text()

    assert "mktemp -d" in publisher
    assert "git clone --depth 1" in publisher
    assert "axom-flood asdma latest" in publisher
    assert "--lookback-days 3" in publisher
    assert "static/data" in publisher
    assert "scripts/verify_impact_publication.py" in publisher
    assert "data/processed/asdma-impact/impact-current.json" in publisher
    assert "scripts/build_pwa_bundle.py" not in publisher
    assert "asdma_status=$?" in publisher
    assert 'exit "$asdma_status"' in publisher
    assert '"$asdma_status" -eq 0' in publisher
    assert "git diff --cached --quiet" in publisher
    assert "git rebase origin/main" in publisher
    assert "git push origin HEAD:main" in publisher


def test_asdma_launch_agent_runs_twice_evening_and_does_not_keep_mac_awake() -> None:
    plist_path = ROOT / "ops/macos/com.axom-flood.asdma-publisher.plist"
    with plist_path.open("rb") as file:
        agent = plistlib.load(file)

    assert agent["Label"] == "com.axom-flood.asdma-publisher"
    assert agent["RunAtLoad"] is True
    assert agent["StartCalendarInterval"] == [
        {"Hour": 20, "Minute": 0},
        {"Hour": 22, "Minute": 0},
    ]
    assert agent.get("KeepAlive") is None
    assert "caffeinate" not in " ".join(agent["ProgramArguments"])
