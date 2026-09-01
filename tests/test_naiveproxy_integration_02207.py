from pathlib import Path


def test_production_installs_naiveproxy_before_app_import():
    source = (Path(__file__).parents[1] / "app" / "production.py").read_text()
    assert source.index("install_naiveproxy()") < source.index("from app.main import app")
    assert "register_naiveproxy_http(app)" in source


def test_integration_registers_engine_subscription_and_common_transaction():
    source = (Path(__file__).parents[1] / "app" / "naiveproxy" / "integration.py").read_text()
    assert 'SUPPORTED_ENGINES += ("naiveproxy",)' in source
    assert 'RUNTIME_ENGINES += ("naiveproxy",)' in source
    assert '("naiveproxy", "naiveproxy", "naiveproxy", "NaiveProxy", "naiveproxy", "uri")' in source
    assert "_patch_client_runtime()" in source
    assert "_naiveproxy_transaction_wrapper" in source
    assert "_patch_mutations" not in source
    assert 'run_hostd_command("naiveproxy.sync"' not in source


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
    assert "candidate_private_key" in source
    assert 'Path(settings["source_private_key_path"])' in source
    assert "_copy_private(" in source
    assert "0o640" in source
    assert 'group="sg-naiveproxy"' in source


def test_first_failed_start_restores_absent_first_install_without_previous_files():
    source = (Path(__file__).parents[1] / "hostd" / "sg_hostd" / "naiveproxy_runtime.py").read_text()
    assert "snapshot = {" in source
    assert '"config": _snapshot(' in source
    assert '"state": _snapshot(' in source
    assert "_restore_snapshot(snapshot, restart=service_was_active)" in source
    assert "active.unlink(missing_ok=True)" in source


def test_ui_injects_protocol_and_real_connections_port_control():
    source = (Path(__file__).parents[1] / "app/naiveproxy/http.py").read_text()
    assert '<input type="checkbox" name="protocols" value="naiveproxy"' in source
    assert "SG_PROTOCOL_ORDER_END" in source
    assert "configured_port" in source
    assert "app.after_request(_inject_naiveproxy_ui)" in source
    assert 'id="sg-naiveproxy-settings"' in source
    assert "data-naive-port" in source
    assert "'/api/naiveproxy/status'" in source
    assert "'/api/naiveproxy/settings'" in source
    assert "JSON.stringify({port: Number(port.value)})" in source


def test_first_assignment_prepares_8447_from_security_tls():
    source = (Path(__file__).parents[1] / "app/naiveproxy/integration.py").read_text()
    assert "assigned_total" in source
    assert "tls_overview()" in source
    assert 'update_connection_settings(' in source
    assert 'DEFAULT_PORT' in source
    assert "NaiveProxy требует настроенный HTTPS" in source


def test_common_clients_apply_includes_naiveproxy():
    source = (Path(__file__).parents[1] / "hostd/sg_hostd/naiveproxy_commands.py").read_text()
    assert 'commands._COMMANDS.get("clients.apply")' in source
    assert 'commands._COMMANDS["clients.apply"] = clients_apply' in source
    assert "naiveproxy_runtime.sync()" in source
    assert 'status="error"' in source
    assert 'combined["naiveproxy"]' in source


def test_hostd_checks_exact_service_pid_before_apply():
    source = (Path(__file__).parents[1] / "hostd/sg_hostd/naiveproxy_listener_patch.py").read_text()
    assert '["ss", "-H", "-ltnp"]' in source
    assert '"systemctl",' in source
    assert '"MainPID"' in source
    assert 're.findall(r"\\bpid=(\\d+)\\b"' in source
    assert "service_pid not in listener_pids" in source
    init_source = (Path(__file__).parents[1] / "hostd/sg_hostd/__init__.py").read_text()
    assert "naiveproxy_listener_patch" in init_source
