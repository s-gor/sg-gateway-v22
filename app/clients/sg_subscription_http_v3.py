from __future__ import annotations

import json

from flask import Flask, Response, abort, jsonify, request

from app.clients.qr import ClientQrError, build_qr_svg
from app.clients.repository import get_client
from app.clients.sg_subscription import (
    SG_SUBSCRIPTION_FORMAT,
    SG_SUBSCRIPTION_VERSION,
    build_compatible_subscription_body,
    build_sg_subscription_document,
    build_sg_subscription_text,
)
from app.clients.sg_subscription_store import (
    build_sg_subscription_url,
    get_client_by_subscription_token,
)

PUBLIC_ENDPOINT = "sg_subscription_v1"
INFO_ENDPOINT = "sg_subscription_v1_info"
QR_ENDPOINT = "sg_subscription_v1_qr"


def register_sg_subscription(app: Flask) -> None:
    if PUBLIC_ENDPOINT not in app.view_functions:
        def feed(token: str):
            client = get_client_by_subscription_token(token)
            if client is None or not client.enabled:
                abort(404)
            document = build_sg_subscription_document(client)
            mode = request.args.get("format", "").strip().lower()
            if mode == "json":
                body = json.dumps(document, ensure_ascii=False, indent=2) + "\n"
                response = Response(body, content_type="application/json; charset=utf-8")
            elif mode == "sg":
                response = Response(
                    build_sg_subscription_text(client),
                    content_type="text/plain; charset=utf-8",
                )
            else:
                response = Response(
                    build_compatible_subscription_body(client),
                    content_type="text/plain; charset=utf-8",
                )
            summary = document.get("summary") or {}
            response.headers["Cache-Control"] = "no-store, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-SG-Subscription-Format"] = SG_SUBSCRIPTION_FORMAT
            response.headers["X-SG-Subscription-Version"] = str(SG_SUBSCRIPTION_VERSION)
            response.headers["X-SG-Subscription-Devices"] = str(summary.get("devices", 0))
            response.headers["X-SG-Subscription-Profiles-Assigned"] = str(summary.get("profiles_assigned", 0))
            response.headers["X-SG-Subscription-Profiles-Ready"] = str(summary.get("profiles_ready", 0))
            return response

        app.add_url_rule(
            "/sg/sub/v1/<token>",
            endpoint=PUBLIC_ENDPOINT,
            view_func=feed,
            methods=["GET"],
        )

    if INFO_ENDPOINT not in app.view_functions:
        def info(client_id: int):
            client = get_client(client_id)
            if client is None:
                abort(404)
            url = build_sg_subscription_url(client)
            if not url:
                return jsonify({
                    "ok": False,
                    "format": SG_SUBSCRIPTION_FORMAT,
                    "version": SG_SUBSCRIPTION_VERSION,
                    "message": "Для клиента не включена SG Subscription",
                }), 409
            return jsonify({
                "ok": True,
                "format": SG_SUBSCRIPTION_FORMAT,
                "version": SG_SUBSCRIPTION_VERSION,
                "url": url,
                "summary": build_sg_subscription_document(client)["summary"],
            })

        app.add_url_rule(
            "/api/clients/<int:client_id>/sg-subscription-v1",
            endpoint=INFO_ENDPOINT,
            view_func=info,
            methods=["GET"],
        )

    if QR_ENDPOINT not in app.view_functions:
        def qr(client_id: int):
            client = get_client(client_id)
            if client is None:
                abort(404)
            url = build_sg_subscription_url(client)
            if not url:
                abort(409)
            try:
                svg = build_qr_svg(url)
            except ClientQrError as exc:
                return Response(str(exc), status=409, mimetype="text/plain")
            return Response(svg, mimetype="image/svg+xml")

        app.add_url_rule(
            "/clients/<int:client_id>/sg-subscription-v1/qr",
            endpoint=QR_ENDPOINT,
            view_func=qr,
            methods=["GET"],
        )

    if not getattr(app, "_sg_subscription_v1_template_context", False):
        def template_context():
            return {"sg_subscription_url": build_sg_subscription_url}

        app.context_processor(template_context)
        setattr(app, "_sg_subscription_v1_template_context", True)
