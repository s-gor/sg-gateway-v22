from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).parents[1]
WRAPPER = ROOT / "deploy/update-from-github-02207.sh"


def _shell_function(source: str, name: str) -> str:
    match = re.search(rf"(?ms)^{re.escape(name)}\(\) \{{\n.*?^\}}$", source)
    assert match is not None, f"shell function is missing: {name}"
    return match.group(0)


def test_02207_base_update_is_exact_source_bound_without_git_credentials():
    source = WRAPPER.read_text(encoding="utf-8")
    runner = _shell_function(source, "run_panel_update")
    core = _shell_function(source, "prepare_panel_update_core")

    assert '${REQUESTED_SOURCE_COMMIT}/deploy/update-from-github-core.sh' in core
    assert 'SG_GATEWAY_GITHUB_REPOSITORY="$REPOSITORY"' in runner
    assert 'SG_GATEWAY_GITHUB_BRANCH="$BRANCH"' in runner
    assert 'SG_GATEWAY_SOURCE_COMMIT="$REQUESTED_SOURCE_COMMIT"' in runner
    assert "SG_GATEWAY_UPDATE_CORE_LIBRARY_ONLY=1" in runner
    assert 'source "$core"' in runner
    assert "prepare_source_light()" in runner
    assert "prepare_source_archive" in runner
    assert "GIT_TERMINAL_PROMPT" not in runner
    assert "GIT_ASKPASS" not in runner
    assert "GCM_INTERACTIVE" not in runner
