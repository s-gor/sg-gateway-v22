from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from flask import Flask, Response, redirect, request, session, url_for

from app.naiveproxy import http as naive_http
from app.security.auth import is_authenticated, should_skip_auth


def _build_app(monkeypatch):
    current = SimpleNamespace(
        host="vpn.example.test",
        port=8447,
        config={
            "domain": "vpn.example.test",
            "certificate_path": "/etc/letsencrypt/live/vpn.example.test/fullchain.pem",
            "private_key_path": "/etc/letsencrypt/live/vpn.example.test/privkey.pem",
        },
    )
    updates: list[tuple[str, str, int, dict]] = []
    commands: list[tuple[str, int]] = []
    state = {"sync_status": "ok"}

    def get_settings(engine: str):
        assert engine == "naiveproxy"
        return current

    def update_settings(engine: str, host: str, port: int, config: dict):
        updates.append((engine, host, int(port), dict(config)))
        return True

    def hostd(command: str, timeout: int):
        commands.append((command, timeout))
        if command == "naiveproxy.status":
            return SimpleNamespace(
                status="ok",
                message="NaiveProxy status",
                payload={
                    "ok": True,
                    "active": True,
                    "runtime_version": "v2.11.2",
                    "checksum_ok": True,
                    "listener": {"owned_by_service": True},
                    "users": 2,
                },
            )
        assert command == "naiveproxy.sync"
        status = state["sync_status"]
        return SimpleNamespace(
            status=status,
            message="NaiveProxy synced" if status == "ok" else "NaiveProxy apply failed",
            payload={"ok": status == "ok"},
        )

    monkeypatch.setattr(naive_http, "get_connection_settings", get_settings)
    monkeypatch.setattr(naive_http, "update_connection_settings", update_settings)
    monkeypatch.setattr(naive_http, "run_hostd_command", hostd)
    monkeypatch.setattr(naive_http, "reserved_ports", lambda: {})
    monkeypatch.setattr(
        naive_http,
        "tls_overview",
        lambda: {
            "https_ready": True,
            "domain": "vpn.example.test",
            "certificate_path": "/etc/letsencrypt/live/vpn.example.test/fullchain.pem",
        },
    )

    app = Flask(__name__)
    app.secret_key = "naiveproxy-http-test"

    @app.before_request
    def protect_panel():
        if should_skip_auth(request.endpoint) or is_authenticated():
            return None
        return redirect(url_for("login", next=request.path))

    @app.get("/login")
    def login():
        return "login"

    @app.get("/connections")
    def connections():
        return Response(
            '<html><body><main>Connections</main>'
            '<section class="cnv1-note-panel sg-ljd-card"></section>'
            '<script>window.base=true;</script></body></html>',
            mimetype="text/html",
        )

    @app.get("/clients")
    def clients():
        return Response(
            "<html><body><!-- SG_PROTOCOL_ORDER_END --></body></html>",
            mimetype="text/html",
        )

    naive_http.register_naiveproxy_http(app)
    return app, updates, commands, state


def _authenticate(client) -> None:
    with client.session_transaction() as values:
        values["authenticated"] = True


def test_naiveproxy_api_is_not_public(monkeypatch):
    app, updates, commands, _ = _build_app(monkeypatch)
    client = app.test_client()

    status = client.get("/api/naiveproxy/status")
    settings = client.post("/api/naiveproxy/settings", json={"port": 9447})

    assert status.status_code == 302
    assert settings.status_code == 302
    assert "/login?next=/api/naiveproxy/status" in status.headers["Location"]
    assert "/login?next=/api/naiveproxy/settings" in settings.headers["Location"]
    assert updates == []
    assert commands == []


def test_connections_uses_native_naiveproxy_panel_after_legacy_content(monkeypatch):
    app, _, _, _ = _build_app(monkeypatch)
    client = app.test_client()
    _authenticate(client)

    response = client.get("/connections")
    assert response.status_code == 200

    root = Path(__file__).resolve().parents[1]
    template = (root / "app/web/templates/connections.html").read_text(encoding="utf-8")
    panel = (root / "app/web/templates/_naiveproxy_panel.html").read_text(encoding="utf-8")
    assert template.count('{% include "_naiveproxy_panel.html" %}') == 1
    assert template.index('_naiveproxy_panel.html') < template.index("cnv1-note-panel")
    assert panel.count('id="sg-naiveproxy-settings"') == 1
    assert "data-naive-host" in panel
    assert "data-naive-port" in panel
    assert "data-naive-runtime" not in panel
    assert "'/api/naiveproxy/status'" in panel
    assert "'/api/naiveproxy/settings'" in panel


def test_protocol_picker_hides_the_configured_port(monkeypatch):
    app, _, _, _ = _build_app(monkeypatch)
    client = app.test_client()
    _authenticate(client)

    response = client.get("/clients")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert body.count('value="naiveproxy"') == 1
    assert "HTTPS-прокси · отдельная ссылка" in body
    assert "TCP 8447" not in body


def test_status_is_secret_safe_and_authenticated(monkeypatch):
    app, _, commands, _ = _build_app(monkeypatch)
    client = app.test_client()
    _authenticate(client)

    response = client.get("/api/naiveproxy/status")
    payload = response.get_json()
    rendered = repr(payload).lower()

    assert response.status_code == 200
    assert payload["runtime"]["checksum_ok"] is True
    assert payload["runtime"]["listener"]["owned_by_service"] is True
    assert "password" not in rendered
    assert "basic_auth" not in rendered
    assert commands == [("naiveproxy.status", 10)]


def test_settings_rejects_form_post_and_applies_json_transaction(monkeypatch):
    app, updates, commands, _ = _build_app(monkeypatch)
    client = app.test_client()
    _authenticate(client)

    form_response = client.post(
        "/api/naiveproxy/settings",
        data={"port": "9447"},
    )
    json_response = client.post(
        "/api/naiveproxy/settings",
        json={"port": 9447},
    )

    assert form_response.status_code == 415
    assert form_response.get_json()["ok"] is False
    assert json_response.status_code == 200
    assert json_response.get_json()["ok"] is True
    assert updates == [
        (
            "naiveproxy",
            "vpn.example.test",
            9447,
            {
                "domain": "vpn.example.test",
                "certificate_path": "/etc/letsencrypt/live/vpn.example.test/fullchain.pem",
                "private_key_path": "/etc/letsencrypt/live/vpn.example.test/privkey.pem",
            },
        )
    ]
    assert commands == [("naiveproxy.sync", 60)]


def test_failed_json_apply_restores_previous_settings(monkeypatch):
    app, updates, commands, state = _build_app(monkeypatch)
    state["sync_status"] = "error"
    client = app.test_client()
    _authenticate(client)

    response = client.post(
        "/api/naiveproxy/settings",
        json={"port": 9447},
    )

    assert response.status_code == 503
    assert response.get_json()["settings_rollback"] is True
    assert updates[0][1:3] == ("vpn.example.test", 9447)
    assert updates[1] == (
        "naiveproxy",
        "vpn.example.test",
        8447,
        {
            "domain": "vpn.example.test",
            "certificate_path": "/etc/letsencrypt/live/vpn.example.test/fullchain.pem",
            "private_key_path": "/etc/letsencrypt/live/vpn.example.test/privkey.pem",
        },
    )
    assert commands == [("naiveproxy.sync", 60)]
