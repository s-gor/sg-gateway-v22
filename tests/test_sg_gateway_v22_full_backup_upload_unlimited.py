from pathlib import Path


def test_python_full_backup_stager_has_no_artificial_size_cap():
    text = Path("app/maintenance/full_backups.py").read_text(encoding="utf-8")
    assert "MAX_UPLOAD_BYTES" not in text
    assert "512 MiB" not in text
    assert "stage_uploaded_full_backup_for_verification" in text


def test_full_backup_nginx_generators_disable_request_size_limit():
    for name in (
        "install.sh",
        "deploy/configure-panel-access.sh",
        "hostd/sg_hostd/full_backup_runtime.py",
    ):
        text = Path(name).read_text(encoding="utf-8")
        assert "client_max_body_size 1024m;" not in text, name
        assert "client_max_body_size 0;" in text, name


def test_verify_ui_uses_same_restore_upload_path_without_size_warning():
    text = Path("app/web/templates/maintenance.html").read_text(encoding="utf-8")
    assert "url_for('restore_full_backup_route')" in text
    assert 'name="backup_action" value="verify"' in text
    assert "data-sg-full-verify-button" in text
    assert "готов к проверке" in text
    assert 'name="backup_action" value="restore_verified"' in text
    assert "максимум 512 MiB" not in text
    assert "размер не ограничен" in text
    assert 'form.dataset.sgConfirmBypass = "1"' in text


def test_panel_route_dispatches_verify_before_restore_job():
    text = Path("app/main.py").read_text(encoding="utf-8")
    assert 'backup_action == "restore_verified"' in text
    assert 'backup_action != "verify"' in text
    assert 'run_hostd_command("backup.full.verify", timeout=180)' in text
    assert 'run_hostd_command("backup.full.restore.start", timeout=20)' in text
    assert text.index("stage_verified_full_backup_for_restore()") < text.index('run_hostd_command("backup.full.restore.start", timeout=20)')
