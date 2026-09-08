from pathlib import Path


def test_core_update_preserves_and_repairs_naiveproxy_runtime():
    source = Path("deploy/update-from-github-core.sh").read_text(encoding="utf-8")
    assert "/hostd/systemd/" in source
    assert '".venv"|"awg3"|"naiveproxy"' in source
    assert 'NAIVE_ROOT="$PREFIX/naiveproxy"' in source
    assert 'sg-gateway-singbox.service "$NAIVE_SERVICE"' in source
    assert "repair_naiveproxy_runtime_if_needed" in source
    assert "naiveproxy_profile_present" in source
    assert 'SG_GATEWAY_SOURCE_ROOT="$PREFIX"' in source
    assert 'bash "$PREFIX/deploy/install-naiveproxy.sh"' in source
    assert '[[ "$SYSTEM_ROOT" == / ]] || return 0' in source


def test_core_update_protects_naiveproxy_from_permission_rewrite():
    source = Path("deploy/update-from-github-core.sh").read_text(encoding="utf-8")
    assert '-o -path "$NAIVE_ROOT"' in source

def test_core_repairs_missing_naiveproxy_only_after_protected_runtime_verification():
    source = Path("deploy/update-from-github-core.sh").read_text(encoding="utf-8")
    deploy_start = source.index("deploy_source() {")
    deploy_end = source.index("\nrestart_panel() {", deploy_start)
    deploy_body = source[deploy_start:deploy_end]
    assert "repair_naiveproxy_runtime_if_needed" not in deploy_body

    stage7 = source.index('run_stage 7 "Проверка HTTPS, credentials, Nginx и runtime" verify_final')
    repair = source.index("repair_naiveproxy_runtime_if_needed", stage7)
    bind = source.index("bind_panel_update_state", stage7)
    finished = source.index("UPDATE_FINISHED=1", stage7)
    assert stage7 < repair < bind < finished

