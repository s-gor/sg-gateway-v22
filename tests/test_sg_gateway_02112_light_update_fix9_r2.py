from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UPDATER = ROOT / "deploy" / "update-from-github.sh"


def source() -> str:
    return UPDATER.read_text(encoding="utf-8")


def test_light_update_uses_runtime_whitelist_only() -> None:
    text = source()
    assert "SG_GATEWAY_02112_LIGHT_UPDATE_FIX9_R2" in text
    assert "sparse-checkout set app hostd deploy" in text
    assert "'/*'" not in text
    for name in ("vendor", "assets", "data", "docs", "tests", ".github"):
        assert f"forbidden in vendor assets data docs tests .github" in text or name in text


def test_light_update_explicitly_rejects_non_runtime_trees() -> None:
    text = source()
    assert "for forbidden in vendor assets data docs tests .github" in text
    assert "LIGHT source unexpectedly contains: $forbidden" in text


def test_light_update_keeps_partial_clone_and_fallback() -> None:
    text = source()
    assert "--depth=1" in text
    assert "--filter=blob:none" in text
    assert "--sparse" in text
    assert "prepare_source_archive()" in text
    assert "LIGHT source failed; falling back to full archive." in text


def test_updater_shell_syntax() -> None:
    result = subprocess.run(
        ["bash", "-n", str(UPDATER)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
