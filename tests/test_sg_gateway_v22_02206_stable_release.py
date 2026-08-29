import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_02206_stable_identity_and_channel():
    manifest = json.loads((ROOT / "release-manifest.json").read_text(encoding="utf-8"))
    assert (ROOT / "VERSION").read_text(encoding="utf-8").strip() == "0.1.0-022.06"
    assert (ROOT / "BUILD-ID").read_text(encoding="utf-8").strip() == "MAIN-02206-STABLE"
    assert manifest["version"] == "0.1.0-022.06"
    assert manifest["build"] == "MAIN-02206-STABLE"
    assert manifest["status"] == "STABLE"
    assert manifest["channel"] == "stable-02206"
    assert manifest["maintenance_updates"]["panel"]["channel"] == "stable-02206"


def test_02206_publication_and_release_workflow_are_complete():
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
    ):
        assert marker in publication
    assert "v0.1.0-022.06" in workflow
    assert "SG-Gateway-0.1.0-022.06-FULL.run" in workflow
    assert "PUBLICATION-02206.md" in workflow
    assert "python -m pytest tests" in workflow
    assert "--verify-only" in workflow


def test_02206_readme_exposes_stable_commands():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "0.1.0-022.06 STABLE" in readme
    assert "stable-02206/deploy/install-from-github.sh" in readme
    assert "stable-02206/deploy/update-from-github.sh" in readme
    assert "stable-02206/deploy/uninstall-from-github.sh" in readme
