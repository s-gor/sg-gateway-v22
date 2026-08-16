"""Production WSGI entrypoint for SG-Gateway 0.1.0-022.04+."""
from __future__ import annotations

from app.main import app
from app.clients.sg_subscription_http_v4 import register_sg_subscription
from app.xray.xmux_http import register_xmux_http

register_sg_subscription(app)
register_xmux_http(app)
