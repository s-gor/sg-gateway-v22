from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_final_archive_does_not_rewrite_tracked_ps1_line_endings() -> None:
    attributes = (ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert "*.ps1 text eol=lf" in attributes
    assert "*.ps1 text eol=crlf" not in attributes

    ps1_files = sorted(
        line for line in subprocess.check_output(
            ["git", "ls-files"],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
        ).splitlines()
        if line.lower().endswith(".ps1")
    )
    assert ps1_files == [
        "scripts/check.ps1",
        "scripts/ci-local.ps1",
        "scripts/run-dev.ps1",
        "scripts/test.ps1",
    ]

    for path in ps1_files:
        eol = subprocess.check_output(
            ["git", "check-attr", "eol", "--", path],
            cwd=ROOT,
            text=True,
            encoding="utf-8",
        )
        assert eol.rstrip().endswith(": eol: lf"), eol
