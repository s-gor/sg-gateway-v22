from pathlib import Path

UPDATER = Path("deploy/update-from-github-core.sh")


def test_panel_update_preserves_awg3_userspace_and_checks_service_state():
    text = UPDATER.read_text(encoding="utf-8")
    assert "sg-gateway-awg3.service" in text
    assert '".venv"|"awg3") continue ;;' in text
    assert '"assets") continue ;;' in text
    assert "verify_runtime_states_unchanged" in text


def test_panel_update_accepts_missing_awg3_as_a_preserved_runtime_state():
    text = UPDATER.read_text(encoding="utf-8")

    # Missing protected paths are fingerprinted explicitly instead of being
    # treated as an updater preflight failure. This is required for servers
    # that entered the v22 line without an AWG3 userspace runtime.
    assert 'digest.update(b"MISSING\\0")' in text
    protected = text[text.index("protected_runtime_paths() {") : text.index("create_safety_backup() {")]
    assert '"/etc/amnezia/amneziawg/awg3.conf"' in protected
    assert '"/etc/systemd/system/sg-gateway-awg3.service"' in protected
    assert '"/opt/sg-gateway/awg3"' in protected

    preflight = text[text.index("preflight() {") : text.index("resolve_source_commit() {")]
    assert 'systemctl is-active --quiet "$AWG3_SERVICE"' not in preflight
    assert 'systemctl is-active --quiet "$HOSTD_SERVICE"' in preflight
    assert 'systemctl is-active --quiet "$PANEL_SERVICE"' in preflight

    deploy = text[text.index("deploy_source() {") : text.index("verify_final() {")]
    assert '".venv"|"awg3") continue ;;' in deploy
    assert 'rm -rf "$stage/vendor/cores"' in deploy

    final = text[text.index("verify_final() {") : text.index("bind_panel_update_state() {")]
    assert 'fail "TLS/AWG3 protected runtime changed during Update"' in final
    assert "verify_runtime_states_unchanged" in final
