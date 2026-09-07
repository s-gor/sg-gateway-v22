import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_02208_stable_release_identity_is_consistent():
    manifest = json.loads((ROOT / "release-manifest.json").read_text(encoding="utf-8"))

    assert (ROOT / "VERSION").read_text(encoding="utf-8").strip() == "0.1.0-022.08"
    assert (ROOT / "BUILD-ID").read_text(encoding="utf-8").strip() == "MAIN-02208-STABLE"
    assert (ROOT / "DEVELOPMENT-VERSION").read_text(encoding="utf-8").strip() == "0.1.0-022.09-dev"

    assert manifest["version"] == "0.1.0-022.08"
    assert manifest["build"] == "MAIN-02208-STABLE"
    assert manifest["status"] == "STABLE"
    assert manifest["channel"] == "stable-02208"
    assert manifest["rebuild_target"] == "0.1.0-022.08"
    assert manifest["next_development_line"] == "0.1.0-022.09"
    assert manifest["maintenance_updates"]["panel"]["channel"] == "stable-02208"
    assert manifest["maintenance_updates"]["panel"]["source"] == "github-stable-02208-exact-commit"
    assert manifest["installer_update"]["version"] == "02208-stable"


def test_02208_release_publication_contract_exists_and_is_pinned():
    workflow = (ROOT / ".github" / "workflows" / "release-02208-stable.yml").read_text(encoding="utf-8")
    publication = (ROOT / "PUBLICATION-02208.md").read_text(encoding="utf-8")

    assert "Release 0.1.0-022.08 Final" in workflow
    assert "v0.1.0-022.08-final" in workflow
    assert "SG-Gateway-0.1.0-022.08-FULL.run" in workflow
    assert 'test "$(cat VERSION)" = "0.1.0-022.08"' in workflow
    assert 'test "$(cat BUILD-ID)" = "MAIN-02208-STABLE"' in workflow
    assert 'manifest["channel"] == "stable-02208"' in workflow
    assert "python -m playwright install --with-deps chromium" in workflow
    assert "python -m pytest tests" in workflow
    assert "PUBLICATION-02208.md" in workflow

    assert "0.1.0-022.08" in publication
    assert "22.08" in publication


def test_02208_installer_and_smoke_workflows_use_current_identity():
    installer = (ROOT / "install.sh").read_text(encoding="utf-8")
    clean = (ROOT / ".github" / "workflows" / "clean-install-awg3-smoke.yml").read_text(encoding="utf-8")
    reinstall = (ROOT / ".github" / "workflows" / "reinstall-after-full-uninstall-smoke.yml").read_text(encoding="utf-8")

    assert 'fail() {' in installer
    assert 'VERSION="0.1.0-022.08"' in installer
    assert 'legacy_resume_file="/root/sg-gateway-02206-installer-resume.env"' in installer
    assert 'mv -f "$legacy_resume_file" "$RESUME_FILE"' in installer

    assert '/root/sg-gateway-02208-installer-resume.env' in clean
    assert '/root/sg-gateway-02206-installer-resume.env' not in clean
    assert '/var/log/sg-gateway-installer-02208.log' in clean

    # The reinstall smoke intentionally exercises legacy-state compatibility.
    assert '/root/sg-gateway-02206-installer-resume.env' in reinstall
