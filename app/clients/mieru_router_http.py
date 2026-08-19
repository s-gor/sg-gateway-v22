from __future__ import annotations

from flask import Response, abort

from app.clients.exports import build_mieru_link, protocol_ready
from app.clients.mieru_router import MieruRouterError, build_mieru_router_uri
from app.clients.qr import ClientQrError, build_qr_svg
from app.clients.repository import get_client, get_device


def _qr_response(payload: str) -> Response:
    try:
        svg = build_qr_svg(payload)
    except ClientQrError as exc:
        return Response(str(exc), status=413, mimetype="text/plain")
    return Response(
        svg,
        mimetype="image/svg+xml",
        headers={"Cache-Control": "no-store, max-age=0"},
    )


def register_mieru_router_http(app) -> None:
    @app.get("/clients/<int:client_id>/mieru-router/qr")
    def mieru_router_qr(client_id: int):
        client = get_client(client_id)
        if client is None:
            abort(404)
        if not protocol_ready(client, "mieru"):
            abort(409)
        try:
            payload = build_mieru_router_uri(build_mieru_link(client).body)
        except MieruRouterError:
            abort(409)
        return _qr_response(payload)

    @app.get("/clients/<int:client_id>/devices/<int:device_id>/mieru-router/qr")
    def device_mieru_router_qr(client_id: int, device_id: int):
        client = get_client(client_id)
        device = get_device(device_id, client_id)
        if client is None or device is None:
            abort(404)
        if not protocol_ready(client, "mieru", device):
            abort(409)
        try:
            payload = build_mieru_router_uri(build_mieru_link(client, device).body)
        except MieruRouterError:
            abort(409)
        return _qr_response(payload)
