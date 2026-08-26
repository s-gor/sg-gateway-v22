from __future__ import annotations

from importlib import import_module
from typing import Any

from flask import Blueprint, Flask, Response, abort, flash, jsonify, redirect, request

from app.clients.exports import build_awg31_config, build_awg31_uri
from app.connections.awg31 import (
    FIELD_NAMES,
    Awg31ValidationError,
    get_settings,
    save_settings,
)
from app.connections.awg31_uri import Awg31UriError


blueprint = Blueprint("awg31", __name__)


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


@blueprint.post("/connections/amneziawg31")
def update_settings_form():
    values = {name: request.form.get(name, "") for name in FIELD_NAMES}
    try:
        save_settings(values)
    except Awg31ValidationError as exc:
        flash(f"Настройки AmneziaWG 3.1 не сохранены: {exc}", "error")
    else:
        flash("Настройки AmneziaWG 3.1 сохранены.", "success")
    return redirect("/connections")


@blueprint.post("/connections/amneziawg31/service/<action>")
def control_service_form(action: str):
    if action not in {"start", "stop", "restart", "status"}:
        abort(404)
    result = _hostd(action)
    flash(
        result.message or f"AWG31 service: {action}",
        "success" if result.status == "ok" else "error",
    )
    return redirect("/connections")


@blueprint.get("/api/connections/awg31")
def api_settings():
    return jsonify(get_settings().as_api())


@blueprint.put("/api/connections/awg31")
@blueprint.patch("/api/connections/awg31")
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


@blueprint.post("/api/connections/awg31/service/<action>")
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


def _download(client_id: int, device_id: int, *, uri: bool = False):
    repository = import_module("app.clients.repository")
    client = repository.get_client(client_id)
    device = repository.get_device(device_id, client_id)
    if client is None or device is None:
        abort(404)
    try:
        export = build_awg31_uri(client, device) if uri else build_awg31_config(client, device)
    except Awg31UriError as exc:
        return Response(
            f"Ошибка формирования AmneziaWG 3.1 URI: {exc}\n",
            status=409,
            mimetype="text/plain",
        )
    return Response(
        export.body,
        mimetype=export.media_type,
        headers={"Content-Disposition": f'attachment; filename="{export.filename}"'},
    )


@blueprint.get("/clients/<int:client_id>/devices/<int:device_id>/protocols/amneziawg31")
def download_config(client_id: int, device_id: int):
    return _download(client_id, device_id)


@blueprint.get(
    "/clients/<int:client_id>/devices/<int:device_id>/protocols/amneziawg31-uri"
)
def download_uri(client_id: int, device_id: int):
    return _download(client_id, device_id, uri=True)


def register_awg31(app: Flask) -> None:
    """Register AWG31 once on this application instance only."""
    if app.extensions.get("awg31_stage2") is True:
        return
    app.register_blueprint(blueprint)
    app.context_processor(_settings_context)
    app.extensions["awg31_stage2"] = True
