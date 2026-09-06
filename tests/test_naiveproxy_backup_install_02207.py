from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_clients_backup_strips_only_server_fields_and_rebinds_naiveproxy():
    source = (ROOT / "hostd/sg_hostd/naiveproxy_backup_patch.py").read_text()
    assert '"naiveproxy", {"host", "port", "domain", "certificate_path", "private_key_path"}' in source
    assert 'payload["host"]' in source
    assert 'payload["port"]' in source
    assert 'payload["password"]' not in source


def test_tls_resyncs_but_full_restore_uses_common_runtime_transaction():
    backup = (ROOT / "hostd/sg_hostd/naiveproxy_backup_patch.py").read_text()
    runtime = (
        ROOT / "hostd/sg_hostd/naiveproxy_client_runtime_patch.py"
    ).read_text()
    commands = (ROOT / "hostd/sg_hostd/naiveproxy_commands.py").read_text()
    assert "operations.run_tls_maintenance = tls_maintenance" in backup
    assert "full.restore_uploaded_full_backup = restore" not in backup
    assert "client_runtime.apply_all_clients = apply_all_clients" in runtime
    assert "commands.apply_all_clients = apply_all_clients" in runtime
    assert 'commands._COMMANDS["clients.apply"]' not in commands


def test_02207_wrappers_refuse_stable_02206_and_install_runtime():
    clean = (ROOT / "deploy/install-from-github-02207.sh").read_text()
    update = (ROOT / "deploy/update-from-github-02207.sh").read_text()
    for source in (clean, update):
        assert '"dev-02207"' in source
        assert "stable-02206" not in source
        assert "install-naiveproxy.sh" in source
        assert "ufw allow 8447/tcp" not in source
        assert "selected TCP port is managed" in source or "runtime transaction completed" in source


def test_hostd_import_installs_backup_and_common_runtime_patches():
    source = (ROOT / "hostd/sg_hostd/__init__.py").read_text()
    assert "naiveproxy_backup_patch" in source
    assert "naiveproxy_client_runtime_patch" in source
    assert "sg_hostd.client_runtime" in source
    assert "sg_hostd.commands" in source
    assert "sg_hostd.full_backup_runtime" in source
    assert "sg_hostd.data_backup_runtime" in source
    assert "sg_hostd.operation_jobs" in source
