from __future__ import annotations

from flask import jsonify, request

from app.connections.settings import get_connection_settings, update_connection_settings
from app.hostd.client import run_hostd_command
from app.naiveproxy.integration import reserved_ports
from app.naiveproxy.runtime import DEFAULT_PORT, NaiveProxyError, validate_port
from app.security.tls import overview as tls_overview


def register_naiveproxy_http(app) -> None:
    if "naiveproxy_status" not in app.view_functions:
        def status():
            settings = get_connection_settings("naiveproxy")
            result = run_hostd_command("naiveproxy.status", timeout=10)
            return jsonify({
                "engine": "naiveproxy",
                "host": settings.host,
                "port": settings.port,
                "default_port": DEFAULT_PORT,
                "runtime": result.payload,
                "status": result.status,
                "message": result.message,
            }), 200 if result.status == "ok" else 503

        app.add_url_rule(
            "/api/naiveproxy/status",
            endpoint="naiveproxy_status",
            view_func=status,
            methods=["GET"],
        )

    if "naiveproxy_settings" not in app.view_functions:
        def settings_update():
            payload = request.get_json(silent=True) or request.form
            tls = tls_overview()
            domain = str(payload.get("domain") or tls.get("domain") or "").strip()
            if not tls.get("https_ready") or not domain:
                return jsonify({"ok": False, "message": "Сначала настройте HTTPS в Security"}), 409
            try:
                port = validate_port(payload.get("port", DEFAULT_PORT), reserved_ports())
            except NaiveProxyError as exc:
                return jsonify({"ok": False, "message": str(exc)}), 400
            config = {
                "domain": domain,
                "certificate_path": str(tls.get("certificate_path") or ""),
                "private_key_path": f"/etc/letsencrypt/live/{domain}/privkey.pem",
            }
            if not update_connection_settings("naiveproxy", domain, port, config):
                return jsonify({"ok": False, "message": "Настройки NaiveProxy отклонены"}), 400
            result = run_hostd_command("naiveproxy.sync", timeout=60)
            code = 200 if result.status == "ok" else 503
            return jsonify({"ok": result.status == "ok", "message": result.message, "runtime": result.payload}), code

        app.add_url_rule(
            "/api/naiveproxy/settings",
            endpoint="naiveproxy_settings",
            view_func=settings_update,
            methods=["POST"],
        )
