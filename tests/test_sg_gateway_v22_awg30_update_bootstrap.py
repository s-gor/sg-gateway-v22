from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_public_update_runs_legacy_awg_cleanup_only_after_core_success() -> None:
    wrapper = (ROOT / "deploy/update-from-github.sh").read_text(encoding="utf-8")
    main = wrapper.split("bootstrap_main()", 1)[1]

    core_call = 'SG_GATEWAY_SOURCE_COMMIT="$commit" bash "$core" "$@"'
    success_guard = '(( rc == 0 )) || return "$rc"'
    compatibility_call = "post_update_awg3_bootstrap"
    assert main.index(core_call) < main.index(success_guard) < main.rindex(compatibility_call)
    assert "app.maintenance.awg3_idle_bootstrap" in wrapper
    assert 'SG_GATEWAY_PREFIX:-/opt/sg-gateway' in wrapper


def test_idle_bootstrap_delegates_to_retirement_cleanup() -> None:
    source = (ROOT / "app/maintenance/awg3_idle_bootstrap.py").read_text(
        encoding="utf-8"
    )
    body = source.split("def bootstrap_idle_awg3()", 1)[1]

    assert "return retire_legacy_awg()" in body
    assert "apply_awg3()" not in body
    assert "_credential_count" not in body
    assert "_snapshot_file" not in body
