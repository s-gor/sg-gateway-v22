"""Production WSGI entrypoint for SG-Gateway 0.1.0-022.04+."""
from __future__ import annotations

from app.clients.mieru_router_http import register_mieru_router_http
from app.clients.router_subscription_http import register_router_subscription
from app.clients.sg_subscription_http_v4 import register_sg_subscription
from app.main import app
from app.xray.xmux_http import register_xmux_http

register_sg_subscription(app)
register_router_subscription(app)
register_mieru_router_http(app)
register_xmux_http(app)
