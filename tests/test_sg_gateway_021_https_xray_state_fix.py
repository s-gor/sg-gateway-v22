from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_https_rollback_state_survives_exit_trap() -> None:
    script = read("deploy/configure-panel-access.sh")
    assert 'SG_HTTPS_BACKUP_DIR=""' in script
    assert "SG_HTTPS_COMMITTED=0" in script
    assert "${SG_HTTPS_COMMITTED:-0}" in script
    assert 'restore_backup "$SG_HTTPS_BACKUP_DIR"' in script
    assert "SG_HTTPS_COMMITTED=1" in script
    assert "committed=0" not in script
    assert "$committed" not in script
    assert 'restore_backup "$backup_dir"' not in script


def test_clients_distinguish_https_from_disabled_profile() -> None:
    clients = read("app/web/templates/clients.html")
    assert "profile.tls_required and not xray_profiles.tls_ready" in clients
    assert "profile.encryption_required and not profile.encryption_ready" in clients
    assert "Сначала включите профиль в Connections" in clients
    assert "Проверьте профиль Xray в Connections" in clients


def test_connections_show_tls_profile_ready_to_enable() -> None:
    connections = read("app/web/templates/connections.html")
    assert "Готов к включению" in connections
    assert "profile.tls_required and xray_profiles.tls_ready" in connections
    assert "Карточки выбираются независимо" in connections
