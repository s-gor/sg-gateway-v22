from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "install.sh"
UNINSTALLER = ROOT / "deploy" / "full-uninstall-ubuntu.sh"
UPDATER = ROOT / "deploy" / "update-from-github.sh"
BUILD_RUN = ROOT / "build-run.sh"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_current_installer_identity_is_02204_and_has_no_02111_tail() -> None:
    text = _text(INSTALLER)
    assert 'VERSION="0.1.0-022.04"' in text
    assert 'INSTALLER_BUILD="02204-full-clean-dual-stack"' in text
    assert 'INSTALL_LOG="/var/log/sg-gateway-installer-02204.log"' in text
    assert 'RESUME_FILE="/root/sg-gateway-02204-installer-resume.env"' in text

    assert 'INSTALLER_BUILD="02111-full-clean-backup-domain"' not in text
    assert 'INSTALL_LOG="/var/log/sg-gateway-installer-02111.log"' not in text
    assert 'RESUME_FILE="/root/sg-gateway-02111-installer-resume.env"' not in text


def test_02112_uninstall_has_current_identity_and_legacy_cleanup() -> None:
    text = _text(UNINSTALLER)
    assert 'UNINSTALL_LOG="/var/log/sg-gateway-full-uninstall-02204.log"' in text
    assert "/root/sg-gateway-02112-installer-resume.env" in text
    assert "/var/log/sg-gateway-installer-02112.log" in text

    # Historical cleanup must remain so older/partial installations can be removed.
    assert "/root/sg-gateway-02111-installer-resume.env" in text
    assert "/var/log/sg-gateway-installer-02111.log" in text


def test_light_update_preserves_local_assets_without_downloading_them() -> None:
    text = _text(UPDATER)
    assert "SG_GATEWAY_02112_LIGHT_UPDATE_ASSET_PRESERVE_FIX10" in text
    assert "prepare_preserved_assets()" in text
    assert "fingerprint_tree_relative()" in text
    assert '"assets") continue ;;' in text
    assert "ASSETS_RECOVERY_DIR" in text
    assert "recovered from Safety Backup" in text
    assert '"$PREFIX/assets/geoip/sg-country-geoip.dat"' in text
    assert "Local assets preserved: OK" in text

    # Light source must remain light: assets are preserved locally, never fetched.
    assert "sparse-checkout set app hostd deploy" in text
    assert "for forbidden in vendor assets data docs tests .github" in text
    assert "sparse-checkout set app hostd deploy assets" not in text


def test_build_run_uses_committed_git_archive_and_version_driven_identity() -> None:
    text = _text(BUILD_RUN)
    assert 'VERSION="$(tr -d' in text
    assert 'BUILD_ID="$(tr -d' in text
    assert 'git -C "$ROOT" archive --format=tar HEAD' in text
    assert 'DEFAULT_BASENAME="SG-Gateway-${VERSION}-FULL"' in text
    assert 'EXPECTED_VERSION="0.1.0-021.12"' not in text


def test_final_publication_metadata_is_consistent() -> None:
    publication = _text(ROOT / "PUBLICATION-02112.md")
    assert "FINAL AWG2" in publication
    assert "0.1.0-022.01" in publication
    assert "Light Update" in publication
    assert "/opt/sg-gateway/assets" in publication

    release = json.loads(_text(ROOT / "release-manifest.json"))
    assert release["version"] == "0.1.0-022.04"
    assert release["status"] == "STABLE"
    assert release["next_development_line"] == "0.1.0-022.05"
    assert release["channel"] == "stable-02204"
    assert release["rebuild_target"] == "0.1.0-022.04"
    assert release["rebuild_policy"]["baseline"] == "0.1.0-021.12"
    assert release["rebuild_policy"]["awg3"] is True
    assert release["safe_update"]["preserve_local_assets"] is True
    assert release["safe_update"]["download_assets"] is False
    assert release["source_integrity"]["mode"] == "git-blob-sha256"
    assert release["source_integrity"]["ci_verified"] is True
    assert release["source_integrity"]["build_run_verified"] is True


def test_source_checksum_inventory_is_strict_and_complete() -> None:
    rows = _text(ROOT / "SOURCE-SHA256SUMS").splitlines()
    listed: set[str] = set()

    for line_no, raw in enumerate(rows, 1):
        if not raw.strip():
            continue
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", raw)
        assert match is not None, f"invalid checksum line {line_no}: {raw!r}"
        path = match.group(2)
        assert path not in listed, f"duplicate checksum path: {path}"
        listed.add(path)

    tracked = set(
        subprocess.check_output(
            ["git", "ls-files"],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
        ).splitlines()
    )
    tracked.discard("SOURCE-SHA256SUMS")
    assert listed == tracked
    assert len(listed) > 400


def test_ci_checks_canonical_integrity_and_full_clean() -> None:
    workflow = _text(ROOT / ".github" / "workflows" / "ci.yml")
    assert "Verify FINAL source integrity" in workflow
    assert '["git", "show", f"HEAD:{path}"]' in workflow
    assert "Git-blob source integrity ok:" in workflow
    assert "Build and verify current FULL package" in workflow
    assert 'OUT="/tmp/SG-Gateway-${VERSION}-FULL.run"' in workflow
