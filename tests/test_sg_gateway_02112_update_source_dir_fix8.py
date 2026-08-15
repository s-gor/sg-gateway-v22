from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UPDATER = ROOT / "deploy" / "update-from-github.sh"


def source() -> str:
    return UPDATER.read_text(encoding="utf-8")


def test_dedicated_update_candidate_validation_uses_source_dir() -> None:
    text = source()
    start = text.index("prepare_source() {")
    end = text.index("\ndeploy_source() {", start)
    block = text[start:end]

    assert "SG_GATEWAY_02112_UPDATE_SOURCE_DIR_FIX8" in block
    assert '"$PREFIX/.venv/bin/python" -B - "$SOURCE_DIR" <<\'PYCHECK\'' in block
    assert '"$source"' not in block


def test_dedicated_update_shell_syntax() -> None:
    result = subprocess.run(
        ["bash", "-n", str(UPDATER)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
