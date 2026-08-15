from __future__ import annotations

import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UPDATER = ROOT / "deploy" / "update-from-github.sh"
INSTALLER = ROOT / "install.sh"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_light_update_uses_partial_clone_without_heavy_trees() -> None:
    text = _text(UPDATER)
    assert "SG_GATEWAY_02112_LIGHT_UPDATE_FIX9" in text
    assert "SG_GATEWAY_02112_LIGHT_UPDATE_FIX9_R2" in text
    assert "--depth=1" in text
    assert "--filter=blob:none" in text
    assert "--sparse" in text
    assert "sparse-checkout set app hostd deploy" in text
    assert "'/*'" not in text
    assert "for forbidden in vendor assets data docs tests .github" in text


def test_light_update_keeps_compatibility_archive_fallback() -> None:
    text = _text(UPDATER)
    assert "prepare_source_archive()" in text
    assert "COMPATIBILITY (full GitHub archive)" in text
    assert "LIGHT source failed; falling back to full archive." in text
    assert "git is not installed; using compatibility source mode." in text


def test_dedicated_update_still_does_not_install_packages_or_cores() -> None:
    text = _text(UPDATER)
    lowered = text.lower()
    assert "apt-get install" not in lowered
    assert "apt install" not in lowered
    assert "install_xray_from_vendor" not in text
    assert "install_mihomo_from_vendor" not in text
    assert "install_sing_box_from_vendor" not in text


def test_clean_install_includes_git_for_future_light_updates() -> None:
    text = _text(INSTALLER)
    start = text.index("stage_system_packages() {")
    end = text.index("\nverify_vendor_core_set() {", start)
    block = text[start:end]
    assert re.search(r"\bsoftware-properties-common\s+git\s+sqlite3\b", block)


def test_shell_syntax() -> None:
    for script in (UPDATER, INSTALLER):
        result = subprocess.run(
            ["bash", "-n", str(script)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, f"{script}: {result.stderr}"
