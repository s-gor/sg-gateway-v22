"""Production WSGI entrypoint for SG-Gateway 0.1.0-022.04+."""
from __future__ import annotations

from app.naiveproxy.integration import install as install_naiveproxy

# Register the 22.07 engine before repository/export modules are imported.
install_naiveproxy()

from app.clients.mieru_router_http import register_mieru_router_http
from app.clients.router_subscription_http import register_router_subscription
from app.clients.sg_subscription_http_v4 import register_sg_subscription
from app.main import app
from app.naiveproxy.http import register_naiveproxy_http
from app.runtime_ui import runtime_engine_state
from app.system_disk_cleanup_http import register_system_disk_cleanup
from app.xray.xmux_http import register_xmux_http


@app.context_processor
def _runtime_ui_helpers():
    return {"runtime_engine_state": runtime_engine_state}


register_sg_subscription(app)
register_router_subscription(app)
register_mieru_router_http(app)
register_xmux_http(app)
register_system_disk_cleanup(app)
register_naiveproxy_http(app)
