from __future__ import annotations

from flask import flash, redirect, request, url_for

from app.security.auth import require_auth
from app.xray.xmux import XmuxError, overview, state_from_config, update_from_form


def register_xmux_http(app) -> None:
    if getattr(app, "_sg_xmux_http_registered", False):
        return

    @app.context_processor
    def sg_xmux_template_context():
        try:
            state = overview()
        except Exception:
            state = state_from_config({})
        return {"xray_xmux": state}

    @app.post("/connections/xmux", endpoint="update_xray_xmux")
    @require_auth
    def update_xray_xmux():
        try:
            state = update_from_form(request.form)
        except XmuxError as exc:
            flash(str(exc), "error")
        else:
            mode_title = next(
                (
                    item["title"]
                    for item in state["mode_options"]
                    if item["value"] == state["mode"]
                ),
                state["mode"],
            )
            flash(f"XMUX сохранён: {mode_title}", "success")
        return redirect(url_for("connections") + "#xray-xmux")

    app._sg_xmux_http_registered = True
