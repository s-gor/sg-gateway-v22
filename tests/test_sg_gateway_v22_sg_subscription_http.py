from __future__ import annotations

from flask import Flask

from app.clients.repository import Client
from app.clients import sg_subscription_http as http


def _client(enabled: bool = True) -> Client:
    return Client(
        id=7,
        name="HTTP test",
        enabled=enabled,
        expires_at=None,
        awg_status="applied",
        xray_status="applied",
    )


def _document(client: Client) -> dict:
    return {
        "format": "sg-subscription",
        "version": 1,
        "scope": "client",
        "client": {"id": client.id, "name": client.name},
        "summary": {
            "devices": 2,
            "profiles_assigned": 3,
            "profiles_ready": 2,
        },
        "devices": [],
    }


def _app() -> Flask:
    app = Flask(__name__)
    http.register_sg_subscription(app)
    return app


def test_register_is_idempotent_and_exposes_both_v1_routes() -> None:
    app = Flask(__name__)
    http.register_sg_subscription(app)
    http.register_sg_subscription(app)

    rules = {rule.endpoint: rule.rule for rule in app.url_map.iter_rules()}
    assert rules[http.PUBLIC_ENDPOINT] == "/sg/sub/v1/<token>"
    assert rules[http.INFO_ENDPOINT] == "/api/clients/<int:client_id>/sg-subscription-v1"


def test_public_feed_returns_json_and_no_cache_security_headers(monkeypatch) -> None:
    client = _client()
    monkeypatch.setattr(http, "get_client_by_subscription_token", lambda token: client)
    monkeypatch.setattr(http, "build_sg_subscription_document", _document)

    response = _app().test_client().get("/sg/sub/v1/sg1_example")

    assert response.status_code == 200
    assert response.get_json()["format"] == "sg-subscription"
    assert response.get_json()["version"] == 1
    assert response.headers["Cache-Control"] == "no-store, max-age=0"
    assert response.headers["Pragma"] == "no-cache"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-SG-Subscription-Format"] == "sg-subscription"
    assert response.headers["X-SG-Subscription-Version"] == "1"


def test_public_feed_hides_invalid_or_disabled_client(monkeypatch) -> None:
    monkeypatch.setattr(http, "get_client_by_subscription_token", lambda token: None)
    assert _app().test_client().get("/sg/sub/v1/bad").status_code == 404

    monkeypatch.setattr(
        http,
        "get_client_by_subscription_token",
        lambda token: _client(enabled=False),
    )
    assert _app().test_client().get("/sg/sub/v1/sg1_disabled").status_code == 404


def test_info_route_reports_disabled_subscription_as_conflict(monkeypatch) -> None:
    client = _client()
    monkeypatch.setattr(http, "get_client", lambda client_id: client)
    monkeypatch.setattr(http, "build_sg_subscription_url", lambda item: "")

    response = _app().test_client().get(
        "/api/clients/7/sg-subscription-v1"
    )

    assert response.status_code == 409
    payload = response.get_json()
    assert payload["ok"] is False
    assert payload["format"] == "sg-subscription"
    assert payload["version"] == 1


def test_info_route_returns_url_and_summary(monkeypatch) -> None:
    client = _client()
    monkeypatch.setattr(http, "get_client", lambda client_id: client)
    monkeypatch.setattr(
        http,
        "build_sg_subscription_url",
        lambda item: "https://gateway.example/sg/sub/v1/sg1_example",
    )
    monkeypatch.setattr(http, "build_sg_subscription_document", _document)

    response = _app().test_client().get(
        "/api/clients/7/sg-subscription-v1"
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["url"].endswith("/sg/sub/v1/sg1_example")
    assert payload["summary"] == {
        "devices": 2,
        "profiles_assigned": 3,
        "profiles_ready": 2,
    }
