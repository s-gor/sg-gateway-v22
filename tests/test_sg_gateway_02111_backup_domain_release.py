from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_02111_scope_is_backup_and_domain_only() -> None:
    version = text("VERSION").strip()
    manifest = json.loads(text("release-manifest.json"))
    assert manifest["version"] == version
    assert manifest["rebuild_policy"]["baseline"] == "0.1.0-021.12"
    assert manifest["portable_full_backup"]["single_file"] is True
    assert manifest["portable_full_backup"]["includes_https_certificates"] is True
    assert manifest["portable_full_backup"]["restore_live_terminal"] is True
    assert manifest["public_endpoint_policy"]["https_domain_preferred_when_ready"] is True


def test_full_restore_is_background_job_with_terminal() -> None:
    main = text("app/main.py")
    commands = text("hostd/sg_hostd/commands.py")
    jobs = text("hostd/sg_hostd/operation_jobs.py")
    runner = text("hostd/sg_hostd/operation_job_runner.py")
    runtime = text("hostd/sg_hostd/full_backup_runtime.py")
    template = text("app/web/templates/operation_job.html")
    assert 'run_hostd_command("backup.full.restore.start", timeout=20)' in main
    assert '"backup.full.restore.start": _full_backup_restore_start' in commands
    assert "def start_full_backup_restore_job()" in jobs
    assert '"full_backup_restore"' in jobs
    assert "def run_full_backup_restore()" in runner
    assert "result = restore_uploaded_full_backup()" in runner
    assert "[Restore 1/7]" in runtime
    assert "[Restore 7/7]" in runtime
    assert "FULL_BACKUP_PANEL_DATA_PERMISSIONS_FIX3" in runtime
    assert "SG_GATEWAY_02111_XRAY_FULL_ACCESS_RESTORE_FIX" in runtime
    assert "SG_GATEWAY_02111_RESTORE_LOCAL_HTTPS_REFRESH_FIX" in runtime
    assert "SG_GATEWAY_02111_RESTORE_CLIENT_RUNTIME_REQUIRED" in runtime
    assert "SG_GATEWAY_02111_PORTABLE_RESTORE_V2" in runtime
    assert "SG_GATEWAY_02111_PORTABLE_HOST_REBIND" in runtime
    assert "SG_GATEWAY_02111_REGENERATE_RUNTIME_FROM_STATE" in runtime
    assert "_refresh_restored_https_from_local_files" in runtime
    assert "_apply_client_runtime_required()" in runtime
    assert "SG_GATEWAY_02111_OPERATION_JOB_PRESERVE_FIX" in runtime
    assert "SG_GATEWAY_02111_RESTORE_HTTPS_BOOTSTRAP_FIX" in runtime
    assert "ЖИВОЙ ТЕРМИНАЛ" in template
    assert "Открыть панель заново" in template
    assert "data-restart-expected" in template


def test_full_backup_carries_https_and_preserves_destination_ip() -> None:
    runtime = text("hostd/sg_hostd/full_backup_runtime.py")
    assert 'Path("/etc/letsencrypt")' in runtime
    assert "SG_GATEWAY_PUBLIC_ADDRESS" in runtime
    assert "destination public IP preserved" in runtime
    assert "security/backups" in runtime
    assert "security/jobs" in runtime
    assert 'TRANSIENT_SECURITY_DIRS = {"backups", "jobs"}' in runtime
    assert "FULL_BACKUP_PANEL_DATA_PERMISSIONS_FIX3" in runtime


def test_nginx_upload_contract_is_durable() -> None:
    access = text("deploy/configure-panel-access.sh")
    runtime = text("hostd/sg_hostd/full_backup_runtime.py")
    assert "SG_GATEWAY_FULL_BACKUP_UPLOAD_FIX1" in access
    assert "client_max_body_size 0;" in access
    assert "proxy_read_timeout 300s;" in access
    assert "def _ensure_full_restore_upload_nginx()" in runtime


def test_domain_endpoint_policy_covers_all_exports() -> None:
    exports = text("app/clients/exports.py")
    mihomo = text("app/mihomo/service.py")

    def block(source: str, name: str, next_name: str) -> str:
        return source[source.index(f"def {name}("):source.index(f"def {next_name}(")]

    public_endpoint = text("app/connections/public_endpoint.py")
    helper = block(exports, "_public_export_host", "_format_endpoint")
    assert "return public_host(*fallbacks)" in helper
    assert "def working_tls_domain()" in public_endpoint
    assert "domain = working_tls_domain()" in public_endpoint
    assert "if domain:" in public_endpoint
    assert "return domain" in public_endpoint
    assert "load_config().public_address" in public_endpoint
    assert public_endpoint.index("return domain") < public_endpoint.index("load_config().public_address")

    awg = block(exports, "build_awg_config", "_xray_profile")
    xray = block(exports, "build_xray_profile_link", "build_xray_link")
    mieru_uri = block(exports, "build_mieru_link", "build_mieru_json")
    mieru_json = block(exports, "build_mieru_json", "build_mihomo_yaml")
    anytls = block(exports, "build_anytls_link", "build_tuic_link")
    tuic = block(exports, "build_tuic_link", "protocol_engine")
    subscription_url = block(exports, "_subscription_base_url", "build_subscription_url")

    assert "endpoint_host = _public_export_host(awg_settings.host)" in awg
    assert "host = _public_export_host(" in xray
    assert "host = _public_export_host(settings.host)" in mieru_uri
    assert "host = _public_export_host(settings.host)" in mieru_json
    assert 'host = _public_export_host(config.get("host", ""))' in anytls
    assert 'host = _public_export_host(config.get("host", ""))' in tuic

    # TLS protocols must use the same live HTTPS domain for SNI as for endpoint selection.
    assert "tls_domain = _working_tls_domain()" in anytls
    assert "tls_domain = _working_tls_domain()" in tuic
    assert 'domain = _working_tls_domain() or str(state.get("tls_domain") or "")' in xray

    # Subscription URL is domain-first too; IP is only the explicit no-HTTPS fallback.
    assert 'public_url = str(tls.get("public_url") or "").strip()' in subscription_url
    assert 'if tls.get("https_ready") and public_url:' in subscription_url
    assert 'return public_url.rstrip("/")' in subscription_url
    assert subscription_url.index("return public_url.rstrip") < subscription_url.index("config = load_config()")

    # Mihomo YAML has its own runtime builder; it must prefer a verified TLS domain.
    yaml_block = block(mihomo, "build_device_yaml", "_yaml_string") if "def _yaml_string(" in mihomo[mihomo.index("def build_device_yaml("):] else mihomo[mihomo.index("def build_device_yaml("):]
    assert 'active_domain = domain if domain and _tls_ready(domain) else ""' in yaml_block
    assert 'host = active_domain or settings["host"]' in yaml_block
    assert "mieru_host = host" in yaml_block
    assert 'f"    server: {_yaml_string(mieru_host)}"' in yaml_block
    assert 'f"    server: {_yaml_string(host)}"' in yaml_block

    # QR/subscription content are generated from these builders, so a ready HTTPS domain
    # must never be replaced by a saved public IP in any public client export.
    assert '"amneziawg": build_awg_config' in exports
    assert '"xray-reality-tcp": lambda item, access=None: build_xray_profile_link' in exports
    assert '"xray-xhttp-reality": lambda item, access=None: build_xray_profile_link' in exports
    assert '"xray-xhttp-tls": lambda item, access=None: build_xray_profile_link' in exports
    assert '"hysteria2": lambda item, access=None: build_xray_profile_link' in exports
    assert '"mieru": build_mieru_link' in exports
    assert '"mieru-json": build_mieru_json' in exports
    assert '"mihomo": build_mihomo_yaml' in exports
    assert '"anytls": build_anytls_link' in exports
    assert '"tuic": build_tuic_link' in exports
    assert '"subscription": build_subscription' in exports


def test_no_traffic_feature_code_is_present() -> None:
    forbidden = ("CLIENT_TRAFFIC", "TRAFFIC2", "TRAFFIC3", "client_traffic")
    for base in (ROOT / "app", ROOT / "hostd"):
        for path in base.rglob("*"):
            if not path.is_file() or path.suffix in {".pyc", ".png", ".ico"}:
                continue
            try:
                body = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for marker in forbidden:
                assert marker not in body, f"{marker} leaked into {path.relative_to(ROOT)}"


def test_xray_permissions_and_restore_success_are_strict() -> None:
    install = text("install.sh")
    runtime = text("hostd/sg_hostd/full_backup_runtime.py")
    client_runtime = text("hostd/sg_hostd/client_runtime.py")
    routing = text("app/routing/runtime.py")
    access = text("deploy/configure-panel-access.sh")
    assert "SG_GATEWAY_02111_XRAY_FULL_ACCESS_POLICY" in install
    assert 'chmod -R 0777 "$root"' in install
    assert '["chmod", "-R", "777", str(root)]' in runtime
    assert "os.chmod(XRAY_CONFIG, 0o777)" in client_runtime
    assert "os.chmod(XRAY_TLS_DIR, 0o777)" in client_runtime
    assert "os.chmod(target, 0o777)" in routing
    assert "xray_full_access" in access
    assert '"certificates": cert_ready' in runtime
    assert '"client_runtime_applied": True' in runtime
    assert "bad=[e for e in r.get('engines',[]) if not e.get('ok')]" in runtime


def test_full_restore_does_not_claim_success_before_runtime_validation() -> None:
    runtime = text("hostd/sg_hostd/full_backup_runtime.py")
    step6 = runtime.index("[Restore 6/7]")
    bootstrap = runtime.index("_refresh_restored_https_from_local_files(allow_xray_inactive=True)", step6)
    clients_first = runtime.index("_apply_client_runtime_required()", bootstrap)
    xray_first = runtime.index("_restart_xray_required()", clients_first)
    strict_refresh = runtime.index("_refresh_restored_https_from_local_files(allow_xray_inactive=False)", xray_first)
    clients_second = runtime.index("_apply_client_runtime_required()", strict_refresh)
    xray_second = runtime.index("_restart_xray_required()", clients_second)
    validate = runtime.index("_validate_runtime_after_restore()", xray_second)
    step7 = runtime.index("[Restore 7/7]", validate)
    assert step6 < bootstrap < clients_first < xray_first < strict_refresh < clients_second < xray_second < validate < step7


def test_portable_restore_does_not_overlay_old_machine_runtime() -> None:
    runtime = text("hostd/sg_hostd/full_backup_runtime.py")
    assert "PORTABLE_STATE_ROOTS" in runtime
    assert 'Path("/etc/letsencrypt")' in runtime
    assert 'Path("/usr/local/share/xray")' in runtime
    restore = runtime[runtime.index("def _restore_payload"):runtime.index("def _ensure_full_restore_upload_nginx")]
    assert "roots = PORTABLE_STATE_ROOTS if preserve_machine_env else ROOT_COMPONENTS" in restore
    assert "_rebind_connection_hosts_to_destination()" in restore
    assert "_clear_generated_runtime_before_rebuild()" in restore
    assert 'UPDATE connection_settings SET host = ?' in runtime
    assert "rolled_back_portable_restore" in runtime
    assert 'Path("/etc/amnezia/amneziawg/awg0.conf")' in runtime
    assert 'Path("/etc/mihomo/config.yaml")' in runtime
    assert 'Path("/etc/sing-box/config.json")' in runtime
    assert 'Path("/usr/local/etc/xray/config.json")' in runtime
    assert '"portable_runtime_regenerated": True' in runtime


def test_safety_rollback_restores_same_machine_runtime_exactly() -> None:
    runtime = text("hostd/sg_hostd/full_backup_runtime.py")
    rollback = runtime[runtime.index("[Restore] ОШИБКА"):runtime.index("archive.unlink", runtime.index("[Restore] ОШИБКА"))]
    assert '_restore_payload(rollback / "payload", preserve_machine_env=False)' in rollback


def test_restore_never_overwrites_live_operation_job_files() -> None:
    runtime = text("hostd/sg_hostd/full_backup_runtime.py")
    assert 'TRANSIENT_SECURITY_DIRS = {"backups", "jobs"}' in runtime
    assert 'parts[index + 1] in TRANSIENT_SECURITY_DIRS' in runtime
    assert '"excluded_history": ["security/backups", "security/jobs"]' in runtime
    # The same member filter is used both while creating new backups and when
    # extracting old V1 backups, so a rollback cannot replace the live log.
    assert 'filter=_portable_tar_filter' in runtime
    assert 'if not _is_internal_history_member(member.name)' in runtime


def test_restore_https_bootstrap_can_defer_xray_check() -> None:
    access = text("deploy/configure-panel-access.sh")
    runtime = text("hostd/sg_hostd/full_backup_runtime.py")
    assert "SG_GATEWAY_02111_RESTORE_HTTPS_BOOTSTRAP_FIX" in access
    assert 'SG_GATEWAY_HTTPS_DEFER_XRAY_CHECK' in access
    assert 'env["SG_GATEWAY_HTTPS_DEFER_XRAY_CHECK"] = "1"' in runtime
    assert "allow_xray_inactive=True" in runtime
    assert "allow_xray_inactive=False" in runtime


def test_full_restore_terminal_has_manual_refresh_button() -> None:
    template = text("app/web/templates/operation_job.html")
    main = text("app/main.py")
    assert 'id="opjob-refresh"' in template
    assert 'Открыть панель заново' in template
    assert "restartExpected" in template
    assert "Панель перезапускается" in template
    assert 'kind == "full_backup_restore"' in main


def test_portable_restore_preserves_destination_session_secret() -> None:
    runtime = text("hostd/sg_hostd/full_backup_runtime.py")
    assert "SG_GATEWAY_02111_RESTORE_SESSION_PRESERVE_FIX" in runtime
    block = runtime[runtime.index("PRESERVE_SG_ENV"):runtime.index("PRESERVE_RUNTIME_ENV")]
    assert '"SG_GATEWAY_SECRET_KEY"' in block
    assert '"SG_GATEWAY_PUBLIC_ADDRESS"' in block


def test_nginx_has_static_restart_page_for_backend_restarts() -> None:
    access = text("deploy/configure-panel-access.sh")
    install = text("install.sh")
    page = text("assets/placeholder/restarting.html")
    for body in (access, install):
        assert "SG_GATEWAY_02111_RESTORE_RESTART_PAGE_FIX" in body
        assert "error_page 502 503 504 =200 /__sg_gateway_restarting;" in body
        assert "restarting.html" in body
    assert "Панель перезапускается" in page
    assert "Открыть панель" in page
