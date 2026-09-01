import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PINNED_INSTALL_SHA = "2e96ea97992509f8ff2fdce8b8d23aa0dc5a1dff"


def test_02206_stable_identity_and_channel():
    manifest = json.loads((ROOT / "release-manifest.json").read_text(encoding="utf-8"))
    assert (ROOT / "VERSION").read_text(encoding="utf-8").strip() == "0.1.0-022.06"
    assert (ROOT / "BUILD-ID").read_text(encoding="utf-8").strip() == "MAIN-02206-STABLE"
    assert manifest["version"] == "0.1.0-022.06"
    assert manifest["build"] == "MAIN-02206-STABLE"
    assert manifest["status"] == "STABLE"
    assert manifest["channel"] == "stable-02206"
    assert manifest["maintenance_updates"]["panel"]["channel"] == "stable-02206"


def test_02206_publication_contract_is_complete_without_github_release():
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


def test_02206_readme_exposes_verified_stable_commands():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "0.1.0-022.06 STABLE" in readme
    assert f"{PINNED_INSTALL_SHA}/deploy/install-from-github.sh" in readme
    assert f"SG_GATEWAY_SOURCE_COMMIT={PINNED_INSTALL_SHA}" in readme
    assert "stable-02206/deploy/update-from-github.sh" in readme
    assert "stable-02206/deploy/uninstall-from-github.sh" in readme
    assert readme.count(f"{PINNED_INSTALL_SHA}/deploy/install-from-github.sh") == 1
    assert readme.count("stable-02206/deploy/update-from-github.sh") == 1
    assert readme.count("stable-02206/deploy/uninstall-from-github.sh") == 1
    assert "sg-gateway-v22/main/deploy/install-from-github.sh" not in readme
    assert "sg-gateway-v22/main/deploy/update-from-github.sh" not in readme
    assert "sg-gateway-v22/main/deploy/full-uninstall-ubuntu.sh" not in readme
