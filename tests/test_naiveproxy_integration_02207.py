from pathlib import Path


def test_production_installs_naiveproxy_before_app_import():
    source = (Path(__file__).parents[1] / "app" / "production.py").read_text()
    assert source.index("install_naiveproxy()") < source.index("from app.main import app")
    assert "register_naiveproxy_http(app)" in source


def test_integration_registers_engine_and_subscription():
    source = (Path(__file__).parents[1] / "app" / "naiveproxy" / "integration.py").read_text()
    assert 'SUPPORTED_ENGINES += ("naiveproxy",)' in source
    assert 'RUNTIME_ENGINES += ("naiveproxy",)' in source
    assert '("naiveproxy", "naiveproxy", "naiveproxy", "NaiveProxy", "naiveproxy", "uri")' in source
    assert 'run_hostd_command("naiveproxy.sync"' in source


def test_hostd_sync_is_database_driven_and_secret_safe():
    source = (Path(__file__).parents[1] / "hostd" / "sg_hostd" / "naiveproxy_runtime.py").read_text()
    assert "FROM device_credentials" in source
    assert "JOIN devices" in source
    assert "JOIN clients" in source
    assert '"users": len(users)' in source
    assert '"users": users' not in source
    assert "Caddyfile.previous" in source
    assert "state.json.previous" in source


def test_hostd_unit_allows_only_naiveproxy_write_paths():
    source = (Path(__file__).parents[1] / "hostd" / "systemd" / "sg-hostd.service").read_text()
    assert "/etc/sg-gateway/naiveproxy" in source
    assert "-/var/lib/sg-gateway" in source


def test_hostd_copies_certbot_key_for_unprivileged_caddy():
    source = (Path(__file__).parents[1] / "hostd" / "sg_hostd" / "naiveproxy_runtime.py").read_text()
    assert 'TLS_PRIVATE_KEY = TLS_DIR / "privkey.pem"' in source
    assert 'shutil.copy2(settings["source_private_key_path"], TLS_PRIVATE_KEY)' in source
    assert "os.chmod(TLS_PRIVATE_KEY, 0o640)" in source
    assert 'group="sg-naiveproxy"' in source


def test_first_failed_start_does_not_require_a_previous_snapshot():
    source = (Path(__file__).parents[1] / "hostd" / "sg_hostd" / "naiveproxy_runtime.py").read_text()
    assert "if previous_config.is_file() and previous_state.is_file():" in source
    assert "CONFIG_PATH.unlink(missing_ok=True)" in source
