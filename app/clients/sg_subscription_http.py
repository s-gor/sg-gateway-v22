from __future__ import annotations

import json

from flask import Flask, Response, abort, jsonify

from app.clients.repository import get_client
from app.clients.sg_subscription import (
    SG_SUBSCRIPTION_FORMAT,
    SG_SUBSCRIPTION_VERSION,
    build_sg_subscription_document,
)
from app.clients.sg_subscription_store import (
    build_sg_subscription_url,
    get_client_by_subscription_token,
)

PUBLIC_ENDPOINT = "sg_subscription_v1"
INFO_ENDPOINT = "sg_subscription_v1_info"


def register_sg_subscription(app: Flask) -> None:
    if PUBLIC_ENDPOINT not in app.view_functions:
        def feed(token: str):
            client = get_client_by_subscription_token(token)
            if client is None or not client.enabled:
                abort(404)
            body = json.dumps(
                build_sg_subscription_document(client),
                ensure_ascii=False,
                indent=2,
            ) + "\n"
            response = Response(body, content_type="application/json; charset=utf-8")
            response.headers["Cache-Control"] = "no-store, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-SG-Subscription-Format"] = SG_SUBSCRIPTION_FORMAT
            response.headers["X-SG-Subscription-Version"] = str(SG_SUBSCRIPTION_VERSION)
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
