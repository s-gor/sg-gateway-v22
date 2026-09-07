from __future__ import annotations

from types import SimpleNamespace

from flask import Flask

from app.naiveproxy import http


def _app() -> Flask:
    app = Flask(__name__)
    http.register_naiveproxy_http(app)
    return app


def _ready_tls() -> dict:
    return {
        "https_ready": True,
        "domain": "new.example.com",
        "certificate_path": "/etc/letsencrypt/live/new.example.com/fullchain.pem",
    }


def _previous_settings():
    return SimpleNamespace(
        host="old.example.com",
        port=8447,
        config={
            "domain": "old.example.com",
            "certificate_path": "/old/fullchain.pem",
            "private_key_path": "/old/privkey.pem",
        },
    )


def test_successful_settings_apply_writes_candidate_once(monkeypatch):
    previous = _previous_settings()
    writes: list[tuple[str, int, dict]] = []
    monkeypatch.setattr(http, "get_connection_settings", lambda engine: previous)
    monkeypatch.setattr(http, "tls_overview", _ready_tls)
    monkeypatch.setattr(http, "reserved_ports", lambda: {})
    monkeypatch.setattr(
        http,
        "update_connection_settings",
        lambda engine, host, port, config: writes.append((host, port, config)) or True,
    )
    monkeypatch.setattr(
        http,
        "run_hostd_command",
        lambda *args, **kwargs: SimpleNamespace(
            status="ok",
            message="NaiveProxy sync",
            payload={"ok": True},
        ),
    )

    response = _app().test_client().post(
        "/api/naiveproxy/settings",
        json={"port": 9447},
    )

    assert response.status_code == 200
    assert response.get_json()["ok"] is True
    assert len(writes) == 1
    assert writes[0][0:2] == ("new.example.com", 9447)


def test_failed_sync_restores_previous_database_settings(monkeypatch):
    previous = _previous_settings()
    writes: list[tuple[str, int, dict]] = []
    monkeypatch.setattr(http, "get_connection_settings", lambda engine: previous)
    monkeypatch.setattr(http, "tls_overview", _ready_tls)
    monkeypatch.setattr(http, "reserved_ports", lambda: {})
    monkeypatch.setattr(
        http,
        "update_connection_settings",
        lambda engine, host, port, config: writes.append((host, port, config)) or True,
    )
    monkeypatch.setattr(
        http,
        "run_hostd_command",
        lambda *args, **kwargs: SimpleNamespace(
            status="error",
            message="TCP port conflict",
            payload={"service": "sg-gateway-naiveproxy.service"},
        ),
    )

    response = _app().test_client().post(
        "/api/naiveproxy/settings",
        json={"port": 9447},
    )

    assert response.status_code == 503
    payload = response.get_json()
    assert payload["ok"] is False
    assert payload["settings_rollback"] is True
    assert writes[0][0:2] == ("new.example.com", 9447)
    assert writes[1] == (
        "old.example.com",
        8447,
        previous.config,
    )


def test_failed_sync_reports_database_rollback_failure(monkeypatch):
    previous = _previous_settings()
    writes: list[tuple[str, int, dict]] = []

    def update(engine, host, port, config):
        writes.append((host, port, config))
        return len(writes) == 1

    monkeypatch.setattr(http, "get_connection_settings", lambda engine: previous)
    monkeypatch.setattr(http, "tls_overview", _ready_tls)
    monkeypatch.setattr(http, "reserved_ports", lambda: {})
    monkeypatch.setattr(http, "update_connection_settings", update)
    monkeypatch.setattr(
        http,
        "run_hostd_command",
        lambda *args, **kwargs: SimpleNamespace(
            status="error",
            message="Caddy validation failed",
            payload={},
        ),
    )

    response = _app().test_client().post(
        "/api/naiveproxy/settings",
        json={"port": 9447},
    )

    assert response.status_code == 500
    payload = response.get_json()
    assert payload["ok"] is False
    assert payload["settings_rollback"] is False
    assert len(writes) == 2
