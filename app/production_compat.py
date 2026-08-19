from __future__ import annotations

import re
from urllib.parse import urlsplit

from flask import Flask, request

_PATCH_FLAG = "_sg_gateway_production_compat_patched"
_ORIGINAL_INIT = Flask.__init__


def _normalize_login_redirect(app: Flask, response):
    if request.endpoint != "login_post" or not (300 <= response.status_code < 400):
        return response

    location = str(response.headers.get("Location") or "").strip()
    if not location:
        return response

    parsed = urlsplit(location)
    if parsed.scheme or parsed.netloc or not parsed.path.startswith("/"):
        response.headers["Location"] = "/"
        return response

    match = re.fullmatch(r"/clients/(\d+)", parsed.path)
    if match:
        from app.clients.repository import get_client

        if get_client(int(match.group(1))) is None:
            response.headers["Location"] = "/clients"
    return response


def install_production_compat() -> None:
    if getattr(Flask, _PATCH_FLAG, False):
        return

    original_init = _ORIGINAL_INIT

    def patched_init(self: Flask, *args, **kwargs) -> None:
        original_init(self, *args, **kwargs)
        if self.import_name != "app.main":
            return

        from app.clients.router_subscription_http import register_router_subscription
        from app.clients.sg_subscription_http_v4 import register_sg_subscription
        from app.xray.xmux_http import register_xmux_http

        register_sg_subscription(self)
        register_router_subscription(self)
        register_xmux_http(self)

        @self.after_request
        def sg_gateway_post_login_redirect_compat(response):
            return _normalize_login_redirect(self, response)

    Flask.__init__ = patched_init
    setattr(Flask, _PATCH_FLAG, True)
