from __future__ import annotations

import json
import re

from flask import Flask, Response, abort, request

from app.clients.router_subscription_store import (
    build_router_subscription_download_url,
    build_router_subscription_url,
    get_router_subscription_access,
)
from app.clients.sg_subscription import (
    SG_ROUTER_SUBSCRIPTION_FORMAT,
    SG_ROUTER_SUBSCRIPTION_VERSION,
    build_router_subscription_document,
)

PUBLIC_ENDPOINT = "router_subscription_v1"


def _safe_filename(value: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "router")).strip("-.")
    return (clean or "router")[:80]


def register_router_subscription(app: Flask) -> None:
    if PUBLIC_ENDPOINT not in app.view_functions:
        def feed(token: str):
            access = get_router_subscription_access(token)
            if access is None:
                abort(404)
            client, device = access
            document = build_router_subscription_document(client, device.id)
            if document is None:
                abort(404)
            body = json.dumps(document, ensure_ascii=False, indent=2) + "\n"
            response = Response(body, content_type="application/json; charset=utf-8")
            response.headers["Cache-Control"] = "no-store, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-SG-Router-Format"] = SG_ROUTER_SUBSCRIPTION_FORMAT
            response.headers["X-SG-Router-Version"] = str(SG_ROUTER_SUBSCRIPTION_VERSION)
            response.headers["X-SG-Router-Profiles"] = str(
                (document.get("summary") or {}).get("profiles", 0)
            )
            if request.args.get("download") == "1":
                filename = _safe_filename(f"{client.name}-{device.name}")
                response.headers["Content-Disposition"] = (
                    f'attachment; filename="SG-Router-{filename}.json"'
                )
            return response

        app.add_url_rule(
            "/sg/router/v1/<token>.json",
            endpoint=PUBLIC_ENDPOINT,
            view_func=feed,
            methods=["GET"],
        )

    if not getattr(app, "_sg_router_subscription_v1_template_context", False):
        def template_context():
            return {
                "router_subscription_url": build_router_subscription_url,
                "router_subscription_download_url": build_router_subscription_download_url,
            }

        app.context_processor(template_context)
        app._sg_router_subscription_v1_template_context = True
