from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_02206_historical_release_artifacts_remain_intact():
    publication = (ROOT / "PUBLICATION-02206.md").read_text(encoding="utf-8")
    for marker in (
        "AWG 2.0",
        "AWG 3.0",
        "AWG 3.1",
        "Full Backup/Restore",
        "Clean Install",
        "Full Uninstall",
        "stable-02206",
    ):
        assert marker in publication
    assert "v0.1.0-022.06-final" not in publication
    assert not (ROOT / ".github" / "workflows" / "release-02206-stable.yml").exists()


def test_02206_history_stays_linked_from_readme():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "SG-Gateway 0.1.0-022.06" in readme
    assert "stable-02206" in readme
    assert "PUBLICATION-02206.md" in readme
