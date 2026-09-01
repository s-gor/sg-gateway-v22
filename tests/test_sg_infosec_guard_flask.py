from __future__ import annotations

from pathlib import Path

from flask import Flask, render_template

from app.security.sg_infosec_guard import (
    AlertStore,
    GuardEngine,
    GuardSettings,
    register_sg_infosec_guard,
)


def build_app(tmp_path: Path, mode: str = "enforce") -> tuple[Flask, GuardEngine]:
    app = Flask(__name__, template_folder="../app/web/templates")
    app.secret_key = "guard-flask-secret"
    engine = GuardEngine(
        settings=GuardSettings(mode=mode),
        alerts=AlertStore(tmp_path / "alerts.jsonl"),
    )
    register_sg_infosec_guard(app, engine=engine)

    @app.route("/", methods=["GET", "TRACE"])
    def index():
        return "ok"

    @app.get("/.env")
    def env_probe():
        return "not found", 404

    @app.get("/api/status")
    def api_status():
        return "ok"

    return app, engine


def test_enforce_mode_blocks_probe_before_route(tmp_path: Path) -> None:
    app, engine = build_app(tmp_path, "enforce")

    response = app.test_client().get("/.env", environ_base={"REMOTE_ADDR": "203.0.113.8"})

    assert response.status_code == 403
    assert response.get_json()["error"] == "request_blocked"
    assert response.headers["Cache-Control"] == "no-store"
    assert engine.alerts.unread_count() == 1


def test_normal_request_passes_and_trace_is_blocked(tmp_path: Path) -> None:
    app, _ = build_app(tmp_path, "enforce")
    client = app.test_client()

    assert client.get("/", environ_base={"REMOTE_ADDR": "203.0.113.9"}).status_code == 200
    assert client.open(
        "/",
        method="TRACE",
        environ_base={"REMOTE_ADDR": "203.0.113.9"},
    ).status_code == 403


def test_monitor_mode_records_probe_without_rejecting(tmp_path: Path) -> None:
    app, engine = build_app(tmp_path, "monitor")

    response = app.test_client().get("/.env", environ_base={"REMOTE_ADDR": "198.51.100.4"})

    assert response.status_code == 404
    assert engine.alerts.unread_count() == 1


def test_guard_partial_renders_with_empty_and_populated_state(tmp_path: Path) -> None:
    template_root = Path("app/web/templates").resolve()
    app = Flask(__name__, template_folder=str(template_root))
    with app.test_request_context("/security"):
        empty = render_template(
            "_sg_infosec_guard.html",
            sg_infosec_guard=None,
            sg_infosec_csrf_token="token",
        )
        populated = render_template(
            "_sg_infosec_guard.html",
            sg_infosec_guard={
                "mode": "enforce",
                "settings": {
                    "mode": "enforce",
                    "max_body_bytes": 65536,
                    "login_requests_per_minute": 20,
                    "api_requests_per_minute": 120,
                    "block_score": 80,
                    "notification_min_score": 70,
                    "notification_webhook": "",
                },
                "counters": {
                    "inspected": 10,
                    "blocked": 2,
                    "rate_limited": 1,
                },
                "alerts": [],
                "unread_count": 0,
                "reputation_count": 3,
            },
            sg_infosec_csrf_token="token",
        )
    assert "Веб-защита" in empty
    assert "Блокирует" in populated
    assert ">3<" in populated
