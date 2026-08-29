from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_public_update_runs_idle_awg3_migration_only_after_core_success() -> None:
    wrapper = (ROOT / "deploy/update-from-github.sh").read_text(encoding="utf-8")
    main = wrapper.split("bootstrap_main()", 1)[1]

    core_call = 'SG_GATEWAY_SOURCE_COMMIT="$commit" bash "$core" "$@"'
    success_guard = '(( rc == 0 )) || return "$rc"'
    migration_call = "post_update_awg3_bootstrap"
    assert main.index(core_call) < main.index(success_guard) < main.rindex(migration_call)
    assert "app.maintenance.awg3_idle_bootstrap" in wrapper
    assert 'SG_GATEWAY_PREFIX:-/opt/sg-gateway' in wrapper


def test_idle_bootstrap_is_transactional_and_never_rewrites_real_awg3_clients() -> None:
    source = (ROOT / "app/maintenance/awg3_idle_bootstrap.py").read_text(
        encoding="utf-8"
    )
    body = source.split("def bootstrap_idle_awg3()", 1)[1]

    assert "if _credential_count() != 0:" in body
    assert body.index("if _credential_count() != 0:") < body.index("apply_awg3()")
    assert "_snapshot_file(AWG3_CONFIG)" in body
    assert "_snapshot_file(cr.ENGINE_SECRETS)" in body
    assert "settings = _settings_snapshot()" in body
    assert "active, enabled = _service_state()" in body
    assert "_restore_file(snapshot)" in body
    assert "_restore_settings(settings)" in body
    assert "_restore_service(active, enabled)" in body
    assert "if not _ready():" in body
