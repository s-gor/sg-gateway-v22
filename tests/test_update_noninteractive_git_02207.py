from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).parents[1]
WRAPPER = ROOT / "deploy/update-from-github-02207.sh"


def _shell_function(source: str, name: str) -> str:
    match = re.search(rf"(?ms)^{re.escape(name)}\(\) \{{\n.*?^\}}$", source)
    assert match is not None, f"shell function is missing: {name}"
    return match.group(0)


def test_02207_base_update_git_is_strictly_noninteractive_and_exact_source_bound():
    source = WRAPPER.read_text(encoding="utf-8")
    runner = _shell_function(source, "run_panel_update")

    assert "GIT_TERMINAL_PROMPT=0" in runner
    assert "GIT_ASKPASS=/bin/false" in runner
    assert 'SG_GATEWAY_GITHUB_REPOSITORY="$REPOSITORY"' in runner
    assert 'SG_GATEWAY_GITHUB_BRANCH="$BRANCH"' in runner
    assert 'SG_GATEWAY_SOURCE_COMMIT="$REQUESTED_SOURCE_COMMIT"' in runner
    assert 'bash "$PREFIX/deploy/update-from-github.sh"' in runner
