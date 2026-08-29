from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def source(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_02110_version_and_exact_placeholder() -> None:
    version = source("VERSION").strip()
    manifest = json.loads(source("release-manifest.json"))
    assert manifest["version"] == version
    assert manifest["rebuild_policy"]["baseline"] == "0.1.0-021.12"
    assert manifest["network_contract"]["public_sni_router_port"] == 443
    assert manifest["network_contract"]["reality_internal_listener"] == "127.0.0.1:7443"
    assert manifest["network_contract"]["browser_https_placeholder_internal"] == "127.0.0.1:7444"


def test_clean_installer_owns_the_full_80_443_contract() -> None:
    installer = source("install.sh")
    assert 'REALITY_INTERNAL_PORT="7443"' in installer
    assert 'PLACEHOLDER_TLS_INTERNAL_PORT="7444"' in installer
    assert 'SG_GATEWAY_REALITY_INTERNAL_PORT=${REALITY_INTERNAL_PORT}' in installer
    assert 'include /etc/nginx/stream-conf.d/sg-gateway-443.conf;' in installer
    assert 'include /etc/nginx/stream-conf.d/*.conf;' not in installer
    assert 'listen 443;' in installer
    assert '${REALITY_SNI} 127.0.0.1:${REALITY_INTERNAL_PORT};' in installer
    assert 'root /var/www/sg-gateway-placeholder;' in installer
    assert 'return 308 https://' not in installer


def test_https_workflow_switches_default_sni_to_placeholder() -> None:
    script = source("deploy/configure-panel-access.sh")
    assert 'XRAY_INTERNAL_PORT="7443"' in script
    assert 'PLACEHOLDER_TLS_INTERNAL_PORT="7444"' in script
    assert 'default 127.0.0.1:$PLACEHOLDER_TLS_INTERNAL_PORT;' in script
    assert 'listen 127.0.0.1:$PLACEHOLDER_TLS_INTERNAL_PORT ssl;' in script
    assert 'listen $PUBLIC_PORT ssl;' in script
    assert 'verify_https_contract' in script


def test_accepted_system_and_device_ui_are_native_source() -> None:
    system = source("app/web/static/sg-system-simple-dials-v1.css")
    memory = source("app/web/static/sg-system-memory-row-bars-v1.css")
    base = source("app/web/templates/base.html")
    detail = source("app/web/templates/client_detail.html")
    collapse_js = source("app/web/static/sg-device-collapse-v1.js")
    collapse_css = source("app/web/static/sg-device-collapse-v4.css")
    assert "System alignment final fix 3 — Disk is the reference" in system
    assert "margin-top: -5px !important;" in system
    assert "margin-top: -16px !important;" in system
    assert "margin-bottom: 6px !important;" in system
    assert "display: none !important;" in memory
    assert "SG_DEVICE_COLLAPSE_V4_LAST_CSS" in base
    assert base.index("SG_DEVICE_COLLAPSE_V4_LAST_CSS") > base.index("sg-mobile-sidebar-v1.css")
    assert "sg-device-collapse-v1.js" in detail
    assert "sg-device-collapsed" in collapse_js
    assert "collapsed device cards v4" in collapse_css.lower()


def test_subscription_source_uses_public_url_and_real_line_breaks() -> None:
    exports = source("app/clients/exports.py")
    access = source("app/clients/access.py")
    main = source("app/main.py")
    detail = source("app/web/templates/client_detail.html")
    assert "def build_subscription_url(" in exports
    assert 'decoded = "\\n".join(links)' in exports
    assert 'decoded = "\\\\n".join(links)' not in exports
    assert "subscription_url = build_subscription_url(client, device)" in access
    assert '@app.get("/sub/<token>")' in main
    assert "Скопировать ссылку" in detail


def _extract_heredoc(body: str, start_marker: str, end_marker: str) -> str:
    start = body.index(start_marker) + len(start_marker)
    end = body.index(end_marker, start)
    return body[start:end].lstrip("\n")


def test_nginx_stream_include_is_idempotent_for_live_freeze(tmp_path: Path) -> None:
    import subprocess

    installer = source("install.sh")
    script = _extract_heredoc(
        installer,
        "python3 - /etc/nginx/nginx.conf <<'PYNGINXMAIN'",
        "PYNGINXMAIN",
    )
    nginx_conf = tmp_path / "nginx.conf"
    nginx_conf.write_text(
        "events {}\nhttp {}\nstream {\n"
        "    include /etc/nginx/stream-conf.d/sg-gateway-443.conf;\n"
        "}\n",
        encoding="utf-8",
    )
    subprocess.run(["python3", "-", str(nginx_conf)], input=script, text=True, check=True)
    result = nginx_conf.read_text(encoding="utf-8")
    assert result.count("sg-gateway-443.conf") == 1
    assert "/etc/nginx/stream-conf.d/*.conf" not in result


def test_nginx_stream_include_deduplicates_direct_and_wildcard(tmp_path: Path) -> None:
    import subprocess

    installer = source("install.sh")
    script = _extract_heredoc(
        installer,
        "python3 - /etc/nginx/nginx.conf <<'PYNGINXMAIN'",
        "PYNGINXMAIN",
    )
    nginx_conf = tmp_path / "nginx.conf"
    nginx_conf.write_text(
        "events {}\nhttp {}\nstream {\n"
        "    include /etc/nginx/stream-conf.d/sg-gateway-443.conf;\n"
        "    include /etc/nginx/stream-conf.d/*.conf;\n"
        "}\n",
        encoding="utf-8",
    )
    subprocess.run(["python3", "-", str(nginx_conf)], input=script, text=True, check=True)
    result = nginx_conf.read_text(encoding="utf-8")
    assert result.count("sg-gateway-443.conf") == 1
    assert "/etc/nginx/stream-conf.d/*.conf" not in result


def test_failure_summary_prefers_failed_command_context() -> None:
    installer = source("install.sh")
    assert "if failed >= 0:" in installer
    assert "selected = lines[start : failed + 1]" in installer


def test_https_helper_stream_include_is_idempotent(tmp_path: Path) -> None:
    import subprocess

    helper = source("deploy/configure-panel-access.sh")
    script = _extract_heredoc(
        helper,
        "ensure_stream_include(){ python3 - \"$NGINX_MAIN\" <<'PY'",
        "PY\n}",
    )
    nginx_conf = tmp_path / "nginx.conf"
    nginx_conf.write_text(
        "events {}\nhttp {}\nstream {\n"
        "    include /etc/nginx/stream-conf.d/sg-gateway-443.conf;\n"
        "}\n",
        encoding="utf-8",
    )
    subprocess.run(["python3", "-", str(nginx_conf)], input=script, text=True, check=True)
    result = nginx_conf.read_text(encoding="utf-8")
    assert result.count("sg-gateway-443.conf") == 1
    assert "/etc/nginx/stream-conf.d/*.conf" not in result
