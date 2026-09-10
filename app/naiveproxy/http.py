from __future__ import annotations

import re

from flask import jsonify, request

from app.connections.settings import get_connection_settings, update_connection_settings
from app.hostd.client import run_hostd_command
from app.naiveproxy.integration import _restore_connection_settings, reserved_ports
from app.naiveproxy.runtime import DEFAULT_PORT, NaiveProxyError, validate_port
from app.security.tls import overview as tls_overview


_PROTOCOL_PICKER_RE = re.compile(
    r'(?P<open><fieldset\b[^>]*class="[^"]*(?:cv10-protocols|dv16-protocol-list)[^"]*"[^>]*>)'
    r'(?P<body>.*?)'
    r'(?P<close></fieldset>)',
    re.DOTALL,
)
_LEGACY_PROTOCOL_HOOK = "<!-- SG_PROTOCOL_ORDER_END -->"


def register_naiveproxy_http(app) -> None:
    # The Connections panel is rendered directly by connections.html.  This
    # after-request hook remains only for the protocol selector used by the
    # Clients workflow, whose list is shared by older templates.
    if not getattr(app, "_naiveproxy_ui_installed", False):
        app.after_request(_inject_naiveproxy_protocol_option)
        app._naiveproxy_ui_installed = True

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
            payload = request.get_json(silent=True)
            if not isinstance(payload, dict):
                return jsonify({
                    "ok": False,
                    "message": "NaiveProxy settings require an application/json request",
                }), 415

            tls = tls_overview()
            domain = str(tls.get("domain") or "").strip()
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
            previous = get_connection_settings("naiveproxy")
            if not update_connection_settings("naiveproxy", domain, port, config):
                return jsonify({"ok": False, "message": "Настройки NaiveProxy отклонены"}), 400

            result = run_hostd_command("naiveproxy.sync", timeout=60)
            if result.status != "ok":
                if str(previous.host or "").strip():
                    restored = update_connection_settings(
                        "naiveproxy",
                        previous.host,
                        previous.port,
                        dict(previous.config),
                    )
                else:
                    restored = _restore_connection_settings(previous)
                if not restored:
                    return jsonify({
                        "ok": False,
                        "message": (
                            f"{result.message}. Восстановить предыдущие "
                            "настройки в БД не удалось"
                        ),
                        "runtime": result.payload,
                        "settings_rollback": False,
                    }), 500
                return jsonify({
                    "ok": False,
                    "message": (
                        f"{result.message}. Предыдущие настройки в БД восстановлены"
                    ),
                    "runtime": result.payload,
                    "settings_rollback": True,
                }), 503

            return jsonify({"ok": True, "message": result.message, "runtime": result.payload}), 200

        app.add_url_rule(
            "/api/naiveproxy/settings",
            endpoint="naiveproxy_settings",
            view_func=settings_update,
            methods=["POST"],
        )


def _inject_naiveproxy_protocol_option(response):
    if response.direct_passthrough or response.mimetype != "text/html":
        return response

    body = response.get_data(as_text=True)
    if 'name="protocols"' not in body and _LEGACY_PROTOCOL_HOOK not in body:
        return response

    tls = tls_overview()
    ready = bool(tls.get("https_ready"))
    disabled = "" if ready else " disabled"
    locked = "" if ready else " is-locked"
    note = (
        "HTTPS-прокси · отдельная ссылка"
        if ready
        else "Требуется HTTPS в Security"
    )

    def option(card_class: str) -> str:
        return (
            f'\n        <label class="{card_class}{locked}">'
            f'<input type="checkbox" name="protocols" value="naiveproxy"{disabled}>'
            f'<span><strong>NaiveProxy</strong><small>{note}</small></span></label>'
        )

    def inject_into_picker(match: re.Match[str]) -> str:
        opening = match.group("open")
        picker_body = match.group("body")
        if 'value="naiveproxy"' in picker_body:
            return match.group(0)

        card_class = (
            "dv16-protocol"
            if "dv16-protocol-list" in opening
            else "cv10-protocol"
        )
        return f'{opening}{picker_body}{option(card_class)}\n      {match.group("close")}'

    updated = _PROTOCOL_PICKER_RE.sub(inject_into_picker, body)
    if updated == body and _LEGACY_PROTOCOL_HOOK in body and 'value="naiveproxy"' not in body:
        updated = body.replace(
            _LEGACY_PROTOCOL_HOOK,
            f'{option("cv10-protocol")}\n{_LEGACY_PROTOCOL_HOOK}',
            1,
        )

    if updated != body:
        response.set_data(updated)

    return response