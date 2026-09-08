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
