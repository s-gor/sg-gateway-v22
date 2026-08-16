from pathlib import Path


SCRIPT = Path("deploy/update-from-github.sh").read_text(encoding="utf-8")


def _section(start: str, end: str) -> str:
    return SCRIPT.split(start, 1)[1].split(end, 1)[0]


def test_update_preserves_awg3_binary_tree_and_does_not_permission_sweep_it():
    deploy = _section("deploy_source() {", "restart_panel() {")
    assert '".venv"|"assets"|"awg3"' in deploy
    assert '-path "$AWG3_ROOT"' in deploy
    assert 'chown -R root:root "$PREFIX"' not in deploy


def test_safety_backup_archives_awg3_config_unit_and_protected_tls_paths():
    backup = _section("create_safety_backup() {", "rollback_update() {")
    assert "etc/amnezia/amneziawg/awg3.conf" in backup
    assert "etc/systemd/system/sg-gateway-awg3.service" in backup
    assert "protected-runtime-paths.txt" in backup
    assert "protected-runtime-before.sha256" in backup

    protected = _section("protected_runtime_paths() {", "create_safety_backup() {")
    assert '"/etc/letsencrypt"' in protected
    assert '"/var/lib/sg-gateway/security/tls-state.json"' in protected
    assert '"/opt/sg-gateway/awg3"' in protected
    assert 'cert="${HTTPS_CERT:-}"' in protected
    assert 'key="${HTTPS_KEY:-}"' in protected
    assert "os.path.realpath" in protected


def test_final_verification_rejects_tls_or_awg3_mutation_and_service_state_drift():
    verify = _section("verify_final() {", "bind_panel_update_state() {")
    assert 'fail "TLS/AWG3 protected runtime changed during Update"' in verify
    assert 'fail "HTTPS certificate state changed during Update"' in verify
    assert 'verify_runtime_states_unchanged "$BACKUP_DIR/service-state.tsv"' in verify

    services = _section("capture_service_states() {", "verify_runtime_states_unchanged() {")
    assert '"$AWG3_SERVICE"' in services
    assert "systemctl is-failed" in services


def test_rollback_restores_awg3_and_external_certificate_material():
    rollback = _section("rollback_update() {", "on_error() {")
    assert '"$AWG3_SERVICE"' in rollback
    assert "/etc/amnezia/amneziawg/awg3.conf" in rollback
    assert "/etc/systemd/system/sg-gateway-awg3.service" in rollback
    assert "protected-runtime-paths.txt" in rollback
    assert 'tar -C / -xpf "$BACKUP_DIR/state.tar"' in rollback
