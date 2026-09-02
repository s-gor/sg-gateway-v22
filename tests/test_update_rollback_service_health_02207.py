from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).parents[1]
CORE = ROOT / "deploy/update-from-github-core.sh"


def _shell_function(source: str, name: str) -> str:
    match = re.search(
        rf"(?ms)^{re.escape(name)}\(\) \{{\n.*?^\}}$",
        source,
    )
    assert match is not None, f"shell function is missing: {name}"
    return match.group(0)


def test_rollback_reports_failed_service_restoration_instead_of_false_ok():
    source = CORE.read_text(encoding="utf-8")
    rollback = _shell_function(source, "rollback_update")

    assert "rollback_failed=0" in rollback
    assert "ROLLBACK INCOMPLETE" in rollback
    assert 'if ! systemctl restart "$service"' in rollback
    assert 'if ! systemctl stop "$service"' in rollback
    assert 'if ! systemctl enable "$service"' in rollback
    assert 'if ! systemctl disable "$service"' in rollback
    assert 'if (( rollback_failed != 0 )); then' in rollback

    incomplete_pos = rollback.index("ROLLBACK INCOMPLETE")
    ok_pos = rollback.index("ROLLBACK OK")
    assert incomplete_pos < ok_pos


def test_error_trap_allows_best_effort_rollback_to_finish_before_exit():
    source = CORE.read_text(encoding="utf-8")
    on_error = _shell_function(source, "on_error")

    # rollback_update performs all restoration attempts and reports its own
    # health. The ERR handler must still preserve the original update rc.
    assert "local rc=$?" in on_error
    assert "rollback_update || true" in on_error
    assert 'exit "$rc"' in on_error
