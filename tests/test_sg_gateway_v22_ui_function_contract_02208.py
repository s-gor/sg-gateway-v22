from __future__ import annotations

from app.clients.repository import create_client, get_primary_device
import app.main as main
from tests.ui.html_contract import FormContract, extract_html_contract, require_contract


def _form(action: str, *names: str, ids: tuple[str, ...] = (), data: tuple[str, ...] = ()) -> FormContract:
    return FormContract(
        action=action,
        method="post",
        names=frozenset(names),
        ids=frozenset(ids),
        data_hooks=frozenset(data),
    )


def _setup_app(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SG_GATEWAY_ADMIN_PASSWORD", "secret")
    monkeypatch.setenv("SG_GATEWAY_SECRET_KEY", "test-secret")
    monkeypatch.setenv("SG_GATEWAY_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("SG_GATEWAY_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("SG_GATEWAY_PUBLIC_ADDRESS", "203.0.113.10")
    monkeypatch.setenv("SG_GATEWAY_COUNTRY_CODE", "fr")

    app = main.create_app()
    app.jinja_env.globals.update(
        {
            "sg_subscription_universal_url": lambda current_client: f"/contracts/{current_client.id}/universal",
            "sg_subscription_native_url": lambda current_client: f"/contracts/{current_client.id}/native",
            "openwrt_subscription_url": lambda current_client, device: f"/contracts/{current_client.id}/{device.id}/openwrt",
            "keenetic_subscription_url": lambda current_client, device: f"/contracts/{current_client.id}/{device.id}/keenetic",
            "router_subscription_url": lambda current_client, device: f"/contracts/{current_client.id}/{device.id}/router",
            "router_subscription_download_url": lambda current_client, device: f"/contracts/{current_client.id}/{device.id}/router.json",
        }
    )
    client = app.test_client()
    client.post("/login", data={"password": "secret"})
    client_id = create_client("Contract Client", "xray")
    assert client_id
    device = get_primary_device(client_id)
    assert device is not None
    monkeypatch.setattr(
        main,
        "read_operation_job",
        lambda job_id: {
            "id": job_id,
            "kind": "xray_apply",
            "status": "running",
            "title": "Contract Job",
            "message": "Contract",
            "log": "line one\nline two",
            "created_at": "2026-09-05T00:00:00Z",
        },
    )
    return app, client, client_id, device.id


def _contract(client, path: str):
    response = client.get(path)
    assert response.status_code == 200, (path, response.status_code)
    return extract_html_contract(response.get_data(as_text=True))


def test_02208_rendered_pages_preserve_backend_and_javascript_contracts(tmp_path, monkeypatch):
    app, client, client_id, device_id = _setup_app(tmp_path, monkeypatch)

    require_contract(
        _contract(client, "/system"),
        ids=(),
        data_hooks=(
            "data-system-activity",
            "data-activity-url",
            "data-sg-memory-refresh",
            "data-sg-cpu-refresh",
            "data-sg-disk-refresh",
        ),
    )

    require_contract(
        _contract(client, "/clients"),
        forms=(
            _form("/clients", "expires_at", "name", "protocols", data=("data-awg-only-note", "data-close-client-form")),
            _form("/clients/apply"),
        ),
        ids=("cv2-dialog", "cv2-search", "cv2-sort", "cv2-table-body", "cv2-apply"),
        data_hooks=("data-open-client-form", "data-client-id", "data-client-name", "data-client-enabled"),
    )

    require_contract(
        _contract(client, f"/clients/{client_id}"),
        forms=(
            _form(f"/clients/{client_id}/delete", data=("data-sg-confirm", "data-sg-confirm-tone")),
            _form(f"/clients/{client_id}/disable"),
            _form(f"/clients/{client_id}/edit", "expires_at", "name", "protocols", data=("data-close-client-edit",)),
            _form(f"/clients/{client_id}/devices", "expires_at", "name", "protocols", data=("data-close-device-form",)),
            _form(f"/clients/{client_id}/devices/{device_id}/disable"),
            _form("/clients/apply", "return_client_id"),
        ),
        ids=(f"device-{device_id}", "dv-edit-client-dialog", "dv46-device-dialog"),
        data_hooks=(
            "data-open-client-edit",
            "data-open-device-form",
            "data-copy-value",
            "data-sg-subscription-v1",
            "data-sg-subscription-dual-v1",
            "data-sg-router-keenetic-subscription-v1",
            "data-sg-router-subscription-v1",
        ),
    )

    require_contract(
        _contract(client, "/connections"),
        forms=(
            _form("/connections/amneziawg", "country_code", "host", "port", "server_public_key"),
            _form("/connections/amneziawg3", "country_code", "host", "port", "server_public_key"),
            _form(
                "/connections/amneziawg31",
                "ContentPaddingAddition", "DisableCookies", "H1", "H2", "H3", "H4",
                "I1", "I2", "I3", "I4", "I5", "Jc", "Jmax", "Jmin",
                "KeepaliveTimeout", "MaxHandshakeAttempts", "RandomTrailers", "RejectAfterTime",
                "RekeyAfterTime", "RekeyTimeout", "S1", "S2", "S3", "S4",
            ),
            _form("/connections/awg-dns", "dns"),
            _form(
                "/connections/mihomo",
                "action", "anytls_enabled", "anytls_padding_scheme", "mieru_enabled",
                "mieru_handshake", "mieru_multiplexing", "mieru_transport",
                "mieru_user_hint_mandatory", "tuic_congestion_controller", "tuic_enabled",
                "tuic_udp_relay_mode",
            ),
            _form("/connections/xmux", "xhttp_extra_client_json", "xhttp_xmux_mode", ids=("xray-xmux-form",)),
            _form("/connections/xray", "public_key", "server_name", "short_id"),
            _form(
                "/connections/xray/profiles",
                "action", "fingerprint", "host", "hysteria2_enabled", "hysteria2_obfs_mode",
                "hysteria2_obfs_password", "hysteria2_obfs_rotate", "reality_tcp_enabled",
                "xhttp_reality_enabled", "xhttp_reality_mode", "xhttp_reality_path",
                "xhttp_tls_enabled", "xhttp_tls_mode", "xhttp_tls_path",
                ids=("xps2-form", "xps2-apply-button"),
            ),
        ),
        ids=("awg-dns", "awg31-settings", "mihomo", "xray-profiles", "xray-xmux", "xray-xmux-form"),
        data_hooks=(
            "data-awg31-profile", "data-profile", "data-profile-panel", "data-runtime-switch",
            "data-salamander-generate", "data-salamander-rotate", "data-xmux-dialog",
            "data-xmux-form", "data-xmux-json", "data-xps2-top-apply",
        ),
    )

    require_contract(
        _contract(client, "/routing"),
        forms=(
            _form("/routing/geofiles/apply", data=("data-sg-confirm",)),
            _form(
                "/routing/geofiles/check",
                "geoip_file", "geoip_url", "geosite_file", "geosite_url", "local_geoip",
                "local_geosite", "roscom_block_ads", "roscom_block_torrent", "roscom_block_windows",
                "source_id", ids=("r096-geofiles-form",), data=("data-source-fields", "data-source-info"),
            ),
            _form(
                "/routing/smart/preview",
                "ads_action", "blocked_action", "custom_block_domains", "custom_block_ips",
                "custom_direct4_domains", "custom_direct4_ips", "custom_direct6_domains",
                "custom_direct6_ips", "custom_warp4_domains", "custom_warp4_ips",
                "custom_warp6_domains", "custom_warp6_ips", "default_action", "local_action",
                "preset", "russia_action", "russia_scope", ids=("r096-smart-form",),
            ),
            _form("/routing/templates/apply", data=("data-sg-confirm",)),
        ),
        ids=("r096-geofiles-form", "r096-smart-form", "r096-user-rules-body", "r096-routing-footer"),
        data_hooks=("data-r096-tab", "data-r096-panel", "data-r096-user-rules-toggle", "data-r096-rule-tab"),
    )

    require_contract(
        _contract(client, "/security"),
        forms=(
            _form("/security/password", "confirm_password", "current_password", "new_password"),
            _form("/security/tls/check", "domain", ids=("secv2-domain-input",)),
            _form("/security/tls/issue"),
        ),
        ids=("password-change", "secv2-domain-input"),
    )

    require_contract(
        _contract(client, "/maintenance"),
        forms=(
            _form("/maintenance/backups"),
            _form("/maintenance/data-backups"),
            _form("/maintenance/data-backups/restore", "backup", "backup_action", ids=("sg-data-backup-file",), data=("data-sg-full-upload", "data-sg-full-verify-button", "data-sg-full-restore-button")),
            _form("/maintenance/full-backups"),
            _form("/maintenance/full-backups/restore", "backup", "backup_action", ids=("sg-full-backup-file",), data=("data-sg-full-upload", "data-sg-full-verify-button", "data-sg-full-restore-button")),
        ),
        ids=("sg-data-backup-file", "sg-full-backup-file", "sg-full-backup-contents", "sg-full-restore-title"),
        data_hooks=("data-sg-full-file", "data-sg-full-verified", "data-sg-confirm"),
    )

    require_contract(
        _contract(client, "/outbounds"),
        forms=(_form("/routing/warp/install"),),
        ids=("warp",),
    )

    require_contract(
        _contract(client, "/help"),
        ids=("help-search", "help-clear", "help-no-results"),
        data_hooks=("data-help-topic", "data-search"),
    )

    require_contract(
        _contract(client, "/recovery"),
        forms=(FormContract(action="", method="post", ids=frozenset({"recovery-restore-form"})),),
        ids=("recovery-restore-form", "recovery-confirm", "recovery-confirm-backup", "recovery-confirm-cancel"),
    )

    require_contract(
        _contract(client, "/operations/contract-job"),
        ids=("opjob-back", "opjob-log", "opjob-message", "opjob-refresh", "opjob-status", "opjob-target"),
        data_hooks=("data-kind", "data-status-url", "data-target-url", "data-restart-expected"),
    )

    anonymous = app.test_client()
    require_contract(
        _contract(anonymous, "/login"),
        forms=(_form("/login", "next", "password"),),
        data_hooks=("data-theme",),
    )
