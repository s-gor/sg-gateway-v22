from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_strict_mihomo_listener_gate_is_removed():
    helper = (ROOT / "app" / "mihomo" / "helper.py").read_text(
        encoding="utf-8"
    )
    assert "def _verify_listeners" not in helper
    assert "_verify_listeners(meta)" not in helper


def test_working_split_runtime_is_restored():
    runtime = (
        ROOT / "hostd" / "sg_hostd" / "client_runtime.py"
    ).read_text(encoding="utf-8")

    mihomo_start = runtime.index("def _apply_mihomo(")
    mihomo_end = runtime.index("\ndef _singbox_binary", mihomo_start)
    mihomo = runtime[mihomo_start:mihomo_end]
    assert 'engine = "mihomo"' in mihomo
    assert "_deployment_rows(engine)" in mihomo
    assert "disable" not in mihomo

    singbox_start = runtime.index("def _apply_singbox(")
    singbox_end = runtime.index("\ndef _apply_sgclient", singbox_start)
    singbox = runtime[singbox_start:singbox_end]
    assert "_render_singbox_config" in singbox
    assert '["systemctl", "restart", SINGBOX_SERVICE]' in singbox
    assert "AnyTLS применён" in singbox
    assert "TUIC v5 применён" in singbox


def test_optional_engines_cannot_fail_client_transaction():
    runtime = (
        ROOT / "hostd" / "sg_hostd" / "client_runtime.py"
    ).read_text(encoding="utf-8")
    block = runtime[runtime.index("def apply_all_clients("):]
    assert "critical_results = [" in block
    assert "_apply_awg()" in block
    assert "_apply_xray()" in block
    assert "optional_results = [" in block
    assert "_apply_mihomo()" in block
    assert "optional_results.extend(_apply_singbox())" in block
    assert "ok = all(result.ok for result in critical_results)" in block


def test_mihomo_candidate_is_mieru_only():
    service = (ROOT / "app" / "mihomo" / "service.py").read_text(
        encoding="utf-8"
    )
    block = service[service.index("def build_candidate("):]
    assert "SG-Gateway working split runtime" in block
    assert 'settings["anytls_enabled"] = False' in block
    assert 'settings["tuic_enabled"] = False' in block


def test_client_links_do_not_depend_on_live_listener_probe():
    exports = (
        ROOT / "app" / "clients" / "exports.py"
    ).read_text(encoding="utf-8")
    assert "mihomo_protocol_active" not in exports
    assert "mihomo_applied_settings" not in exports
    assert 'body = f"mierus://' in exports
    assert "build_anytls_link" in exports
    assert "build_tuic_link" in exports


def test_installer_keeps_fixed_stage7_contract():
    installer = (ROOT / "install.sh").read_text(encoding="utf-8")
    assert "response.status_code in (200, 409)" in installer

def test_mihomo_helper_does_not_control_independent_singbox():
    helper = (ROOT / "app" / "mihomo" / "helper.py").read_text(encoding="utf-8")
    assert "LEGACY_SINGBOX_SERVICE" not in helper
    assert "LEGACY_SINGBOX_MARKER" not in helper
    assert '"disable", "--now", "sg-gateway-singbox.service"' not in helper
