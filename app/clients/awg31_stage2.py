from __future__ import annotations

from importlib import import_module
from typing import Any
from urllib.parse import quote, urlencode

from flask import Blueprint, Response, abort, flash, jsonify, redirect, request
from jinja2 import ChoiceLoader, DictLoader, PrefixLoader

from app.connections.awg31 import (
    Awg31ValidationError,
    ENDPOINT,
    FIELD_NAMES,
    get_settings,
    save_settings,
)

_BLUEPRINT = Blueprint("awg31", __name__)
_TEMPLATE_WRAPPER = """{% extends 'stage1/connections.html' %}
{% block content %}
{{ super() }}
{% include '_awg31_panel.html' %}
{% endblock %}
"""


def _hostd(action: str):
    main = import_module("app.main")
    return main.run_hostd_command(f"awg31.{action}")


def _settings_context() -> dict[str, Any]:
    if request.endpoint != "connections":
        return {}
    return {
        "awg31_settings": get_settings(),
        "awg31_fields": FIELD_NAMES,
        "awg31_status": _hostd("status"),
    }


@_BLUEPRINT.post("/connections/amneziawg31")
def update_settings_form():
    values = {name: request.form.get(name, "") for name in FIELD_NAMES}
    try:
        save_settings(values)
    except Awg31ValidationError as exc:
        flash(f"Настройки AmneziaWG 3.1 не сохранены: {exc}", "error")
    else:
        flash("Настройки AmneziaWG 3.1 сохранены.", "success")
    return redirect("/connections")


@_BLUEPRINT.post("/connections/amneziawg31/service/<action>")
def control_service_form(action: str):
    if action not in {"start", "stop", "restart", "status"}:
        abort(404)
    result = _hostd(action)
    flash(
        result.message or f"AWG31 service: {action}",
        "success" if result.status == "ok" else "error",
    )
    return redirect("/connections")


@_BLUEPRINT.get("/api/connections/awg31")
def api_settings():
    return jsonify(get_settings().as_api())


@_BLUEPRINT.put("/api/connections/awg31")
@_BLUEPRINT.patch("/api/connections/awg31")
def api_update_settings():
    payload = request.get_json(silent=True) or {}
    values = payload.get("parameters", payload)
    if not isinstance(values, dict):
        return jsonify({"error": "parameters must be an object"}), 400
    try:
        settings = save_settings(values)
    except Awg31ValidationError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(settings.as_api())


@_BLUEPRINT.post("/api/connections/awg31/service/<action>")
def api_control_service(action: str):
    if action not in {"start", "stop", "restart", "status"}:
        abort(404)
    result = _hostd(action)
    return jsonify(
        {
            "command": result.command,
            "status": result.status,
            "message": result.message,
            "payload": result.payload,
        }
    ), (200 if result.status != "error" else 403)


def _export_parts(client, device):
    exports = import_module("app.clients.exports")
    config = exports._deployment_config(client, "amneziawg31", device)
    settings = get_settings()
    return exports, config, settings


def build_awg31_config(client, device=None):
    exports, config, settings = _export_parts(client, device)
    parameter_lines = "\n".join(
        f"{name} = {settings.parameters[name]}" for name in FIELD_NAMES
    )
    body = f"""# SG-Gateway AmneziaWG 3.1
# Access: {exports._label(client, device)}
# Profile: awg31
# Transport: UDP

[Interface]
PrivateKey = {config.get('private_key', '')}
Address = {config.get('address', '')}
DNS = {settings.dns}
{parameter_lines}

[Peer]
PublicKey = {config.get('server_public_key') or settings.server_public_key}
Endpoint = {ENDPOINT}
AllowedIPs = {config.get('allowed_ips', '0.0.0.0/0, ::/0')}
PersistentKeepalive = {config.get('persistent_keepalive', 25)}
"""
    return exports.ClientExport(
        filename=f"sg-gateway-{exports._slug(client, device)}-amneziawg31.conf",
        media_type="text/plain; charset=utf-8",
        body=body,
    )


def build_awg31_uri(client, device=None):
    exports, config, settings = _export_parts(client, device)
    query_values = {
        "transport": "udp",
        "address": str(config.get("address", "")),
        "dns": settings.dns,
        "public_key": str(config.get("server_public_key") or settings.server_public_key),
        "allowed_ips": str(config.get("allowed_ips", "0.0.0.0/0, ::/0")),
        "persistent_keepalive": str(config.get("persistent_keepalive", 25)),
        **{name: str(settings.parameters[name]) for name in FIELD_NAMES},
    }
    private_key = quote(str(config.get("private_key", "")), safe="")
    label = quote(exports._label(client, device), safe="")
    body = f"awg31://{private_key}@{ENDPOINT}?{urlencode(query_values, quote_via=quote)}#{label}"
    return exports.ClientExport(
        filename=f"sg-gateway-{exports._slug(client, device)}-amneziawg31-uri.txt",
        media_type="text/plain; charset=utf-8",
        body=body,
    )


def _download(client_id: int, device_id: int, *, uri: bool = False):
    repository = import_module("app.clients.repository")
    client = repository.get_client(client_id)
    device = repository.get_device(client_id, device_id)
    if client is None or device is None:
        abort(404)
    export = build_awg31_uri(client, device) if uri else build_awg31_config(client, device)
    return Response(
        export.body,
        mimetype=export.media_type,
        headers={"Content-Disposition": f'attachment; filename="{export.filename}"'},
    )


@_BLUEPRINT.get("/clients/<int:client_id>/devices/<int:device_id>/protocols/amneziawg31")
def download_config(client_id: int, device_id: int):
    return _download(client_id, device_id)


@_BLUEPRINT.get("/clients/<int:client_id>/devices/<int:device_id>/protocols/amneziawg31-uri")
def download_uri(client_id: int, device_id: int):
    return _download(client_id, device_id, uri=True)


def install_exports() -> None:
    exports = import_module("app.clients.exports")
    exports.build_awg31_config = build_awg31_config
    exports.build_awg31_uri = build_awg31_uri
    original_protocol_engine = exports.protocol_engine
    original_build_protocol_export = exports.build_protocol_export

    def protocol_engine(kind: str) -> str:
        if kind in {"amneziawg31", "amneziawg31-uri"}:
            return "amneziawg31"
        return original_protocol_engine(kind)

    def build_protocol_export(client, kind: str, device=None):
        if kind == "amneziawg31":
            return build_awg31_config(client, device)
        if kind == "amneziawg31-uri":
            return build_awg31_uri(client, device)
        return original_build_protocol_export(client, kind, device)

    exports.protocol_engine = protocol_engine
    exports.build_protocol_export = build_protocol_export


def install_access() -> None:
    access = import_module("app.clients.access")
    original = access.build_access_cards

    def build_access_cards(client, device=None):
        cards = original(client, device)
        deployments = access._deployment_map(client, device)
        deployment = deployments.get("amneziawg31")
        if deployment is None or any(card.kind == "amneziawg31" for card in cards):
            return cards
        try:
            status = access._status(client, device, deployment)
            export_url, _ = access._urls(client, device, "amneziawg31")
            uri_url, _ = access._urls(client, device, "amneziawg31-uri")
            cards.append(
                access.AccessCard(
                    kind="amneziawg31",
                    title="AmneziaWG 3.1",
                    status=status,
                    description="Независимый AWG31-профиль на awg31.internal:587/UDP.",
                    primary_action="Скачать конфигурацию",
                    export_url=export_url,
                    qr_url="",
                    payload=build_awg31_config(client, device).body if status == "applied" else "",
                    show_qr=False,
                    tertiary_url=uri_url,
                    tertiary_label="Скачать URI",
                )
            )
        except Exception as exc:
            cards.append(
                access._error_card(
                    client,
                    device,
                    kind="amneziawg31",
                    title="AmneziaWG 3.1",
                    exc=exc,
                )
            )
        return cards

    access.build_access_cards = build_access_cards


def install_flask_hook() -> None:
    from flask import Flask

    if getattr(Flask, "_awg31_stage2_installed", False):
        return
    original_init = Flask.__init__

    def init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        original_loader = self.jinja_loader
        if original_loader is not None:
            self.jinja_loader = ChoiceLoader(
                [
                    DictLoader({"connections.html": _TEMPLATE_WRAPPER}),
                    PrefixLoader({"stage1": original_loader}),
                    original_loader,
                ]
            )
        self.register_blueprint(_BLUEPRINT)
        self.context_processor(_settings_context)

    Flask.__init__ = init
    Flask._awg31_stage2_installed = True


def install() -> None:
    install_exports()
    install_access()
    install_flask_hook()
