from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_installer_publishes_https_transaction_runtime() -> None:
    install = read("install.sh")
    assert 'DEFAULT_PANEL_PORT="63443"' in install
    assert 'BACKEND_PORT="18080"' in install
    assert 'chmod 0755 "$PREFIX/deploy/configure-panel-access.sh"' in install
    assert "SG_GATEWAY_PORT=18080" in install
    assert "SG_GATEWAY_PUBLIC_PORT=63443" in install


def test_hostd_exposes_transaction_jobs() -> None:
    jobs = read("hostd/sg_hostd/operation_jobs.py")
    commands = read("hostd/sg_hostd/commands.py")
    assert 'PANEL_ACCESS_SCRIPT = Path("/opt/sg-gateway/deploy/configure-panel-access.sh")' in jobs
    assert "start_tls_issue_job" in jobs
    assert "run_tls_maintenance" in jobs
    assert '"tls.issue.start"' in commands
    assert '"tls.renew"' in commands
    assert '"tls.rollback"' in commands
    assert '"systemd-run"' in jobs


def test_security_ui_uses_public_and_backend_ports() -> None:
    security = read("app/web/templates/security.html")
    operation = read("app/web/templates/operation_job.html")
    tls = read("app/security/tls.py")
    helper = read("app/security/tls_helper.py")
    assert "TCP {{ tls.public_port }}" in security
    assert "127.0.0.1:{{ tls.backend_port }}" in security
    assert "Продолжаю этот же терминал по защищённому адресу" in operation
    assert "результат откроется только по кнопке" in operation
    assert "window.location.replace(targetUrl)" not in operation
    assert "public_port" in tls
    assert "backend_port" in tls
    assert 'return _state_dir() / "tls-state.json"' in tls
    assert 'SCRIPT = Path("/opt/sg-gateway/deploy/configure-panel-access.sh")' in helper
