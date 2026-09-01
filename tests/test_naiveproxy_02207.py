import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))
from app.naiveproxy import runtime


def settings(port=8447):
    return runtime.NaiveProxySettings(
        domain="vpn.example.com",
        port=port,
        certificate_path="/etc/letsencrypt/live/vpn.example.com/fullchain.pem",
        private_key_path="/etc/letsencrypt/live/vpn.example.com/privkey.pem",
    )


def test_default_port_is_8447_and_never_claims_443():
    user = runtime.NaiveProxyUser("alice", "a" * 32)
    config = runtime.render_caddyfile(settings(), [user])
    assert runtime.DEFAULT_PORT == 8447
    assert ":8447, vpn.example.com:8447" in config
    assert ":443" not in config
    assert "auto_https disable_redirects" in config


def test_caddyfile_uses_existing_certificate_and_probe_resistance():
    user = runtime.NaiveProxyUser("alice", "b" * 32)
    config = runtime.render_caddyfile(settings(), [user])
    assert "tls /etc/letsencrypt/live/vpn.example.com/fullchain.pem /etc/letsencrypt/live/vpn.example.com/privkey.pem" in config
    assert "basic_auth alice " + "b" * 32 in config
    assert "hide_ip" in config
    assert "hide_via" in config
    assert "probe_resistance" in config
    assert "exclude http.log.error" in config


def test_caddyfile_rejects_credential_directive_injection():
    user = runtime.NaiveProxyUser(
        "alice",
        "safe-password-1234 } forward_proxy {",
    )
    with pytest.raises(runtime.NaiveProxyError, match="безопасных символов"):
        runtime.render_caddyfile(settings(), [user])


def test_port_validation_rejects_sg_gateway_conflict():
    with pytest.raises(runtime.NaiveProxyError, match="Reality"):
        runtime.validate_port(443, {443: "VLESS Reality"})


def test_client_uri_contains_explicit_8447_and_safe_credentials():
    user = runtime.NaiveProxyUser("alice.one", "safe-password-with-very-long-value")
    uri = runtime.build_client_uri(settings(), user, "Телефон")
    assert uri.startswith(
        "naive+https://alice.one:safe-password-with-very-long-value@vpn.example.com:8447"
    )
    assert uri.endswith("#%D0%A2%D0%B5%D0%BB%D0%B5%D1%84%D0%BE%D0%BD")


def test_runtime_state_is_atomic_and_private(tmp_path):
    config_dir = tmp_path / "etc"
    state_dir = tmp_path / "state"
    state = runtime.write_runtime(
        settings(),
        [runtime.NaiveProxyUser("alice", "c" * 32)],
        config_dir=config_dir,
        state_dir=state_dir,
    )
    assert json.loads((state_dir / "state.json").read_text())["settings"]["port"] == 8447
    assert (config_dir / "Caddyfile").stat().st_mode & 0o777 == 0o640
    assert (state_dir / "state.json").stat().st_mode & 0o777 == 0o600
    assert state["users"][0]["password"] == "c" * 32


def test_redaction_hides_caddy_and_uri_passwords():
    text = "basic_auth alice secret-password\nnaive+https://alice:uri-secret@example.com:8447"
    redacted = runtime.redact(text)
    assert "secret-password" not in redacted
    assert "uri-secret" not in redacted
    assert redacted.count("***") == 2


def test_service_is_unprivileged_and_restricted():
    unit = (Path(__file__).parents[1] / "deploy" / "sg-gateway-naiveproxy.service").read_text()
    assert "User=sg-naiveproxy" in unit
    assert "NoNewPrivileges=true" in unit
    assert "ProtectSystem=strict" in unit
    assert "AmbientCapabilities=CAP_NET_BIND_SERVICE" in unit


def test_installer_pins_archive_and_records_binary_digest_separately():
    installer = (Path(__file__).parents[1] / "deploy" / "install-naiveproxy.sh").read_text()
    assert 'RUNTIME_VERSION="v2.11.2-naive"' in installer
    assert 'RUNTIME_ARCHIVE_SHA256="19eccb7321dd877a5fb4a3dba6ef1b745185188b616c96cc6201f1a1fc0380a8"' in installer
    assert 'printf \'%s  %s\\n\' "$RUNTIME_ARCHIVE_SHA256" "$archive" | sha256sum -c -' in installer
    assert 'binary_sha256="$(sha256sum "$PREFIX/bin/caddy"' in installer
    assert "RUNTIME_BINARY_SHA256=$binary_sha256" in installer
    assert "RUNTIME_ARCHIVE_SHA256=$RUNTIME_ARCHIVE_SHA256" in installer
    assert "releases/latest" not in installer
    assert "http.handlers.forward_proxy" in installer


def test_runtime_update_preserves_previous_state(tmp_path):
    config_dir = tmp_path / "etc"
    state_dir = tmp_path / "state"
    first = runtime.NaiveProxyUser("one", "x" * 32, client_id="1")
    second = runtime.NaiveProxyUser("two", "y" * 32, client_id="2")
    runtime.write_runtime(settings(), [first], config_dir=config_dir, state_dir=state_dir)
    runtime.write_runtime(settings(9447), [second], config_dir=config_dir, state_dir=state_dir)
    previous = json.loads((state_dir / "state.json.previous").read_text())
    current = json.loads((state_dir / "state.json").read_text())
    assert previous["settings"]["port"] == 8447
    assert previous["users"][0]["client_id"] == "1"
    assert current["settings"]["port"] == 9447
    assert current["users"][0]["client_id"] == "2"


def test_empty_user_set_disables_proxy_but_keeps_tls_decoy():
    config = runtime.render_caddyfile(settings(), [])
    assert "forward_proxy" not in config
    assert "file_server" in config
    assert ":8447" in config


def test_installer_grants_service_read_only_config_access():
    installer = (Path(__file__).parents[1] / "deploy" / "install-naiveproxy.sh").read_text()
    assert 'install -d -o root -g sg-naiveproxy -m 0750 "$CONFIG_DIR"' in installer
    assert 'chmod 0640 "$CONFIG_DIR/Caddyfile"' in installer
