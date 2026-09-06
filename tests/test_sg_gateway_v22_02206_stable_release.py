from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_02206_historical_release_artifacts_remain_intact():
    publication = (ROOT / "PUBLICATION-02206.md").read_text(encoding="utf-8")
    workflow = (ROOT / ".github" / "workflows" / "release-02206-stable.yml").read_text(encoding="utf-8")
    for marker in (
        "AWG 2.0",
        "AWG 3.0",
        "AWG 3.1",
        "Full Backup/Restore",
        "Clean Install",
        "Full Uninstall",
        "stable-02206",
        "v0.1.0-022.06-final",
    ):
        assert marker in publication
    assert "TAG: v0.1.0-022.06-final" in workflow
    assert "TITLE: SG-Gateway 0.1.0-022.06 Final" in workflow
    assert "SG-Gateway-0.1.0-022.06-FULL.run" in workflow
    assert "PUBLICATION-02206.md" in workflow
    assert "python -m pytest tests" in workflow
    assert "--verify-only" in workflow
    assert "--latest" in workflow


def test_02206_history_stays_linked_from_readme():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "PUBLICATION-02206.md" in readme
