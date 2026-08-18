from __future__ import annotations

from flask import Flask

from app.clients.repository import Client
from app.clients import sg_subscription_http_v3 as http
from app.security.auth import should_skip_auth


def _client() -> Client:
    return Client(id=51, name="HTTP v3", enabled=True, expires_at=None, awg_status="applied", xray_status="applied")


def _document() -> dict:
    return {
        "format": "sg-subscription",
        "version": 1,
        "scope": "client",
        "client": {"id": 51, "name": "HTTP v3"},
        "summary": {"devices": 2, "profiles_assigned": 6, "profiles_ready": 5},
        "devices": [],
    }


def _app(monkeypatch) -> Flask:
    client = _client()
    monkeypatch.setattr(http, "get_client_by_subscription_token", lambda token: client)
    monkeypatch.setattr(http, "build_sg_subscription_document", lambda item: _document())
    monkeypatch.setattr(http, "build_compatible_subscription_body", lambda item: "dmxlc3M6Ly9leGFtcGxlCg==")
    monkeypatch.setattr(http, "build_sg_subscription_text", lambda item: "# SG-SUBSCRIPTION/1\nvless://example\n")
    app = Flask(__name__)
    http.register_sg_subscription(app)
    http.register_sg_subscription(app)
    return app


def test_default_feed_is_base64_compatible_transport(monkeypatch) -> None:
    response = _app(monkeypatch).test_client().get("/sg/sub/v1/sg1_example")
    assert response.status_code == 200
    assert response.mimetype == "text/plain"
    assert response.get_data(as_text=True) == "dmxlc3M6Ly9leGFtcGxlCg=="
    assert response.headers["X-SG-Subscription-Devices"] == "2"
    assert response.headers["X-SG-Subscription-Profiles-Assigned"] == "6"
    assert response.headers["X-SG-Subscription-Profiles-Ready"] == "5"


def test_format_sg_returns_human_readable_native_envelope(monkeypatch) -> None:
    response = _app(monkeypatch).test_client().get("/sg/sub/v1/sg1_example?format=sg")
    assert response.status_code == 200
    assert response.mimetype == "text/plain"
    assert response.get_data(as_text=True) == "# SG-SUBSCRIPTION/1\nvless://example\n"


def test_format_json_returns_structured_document(monkeypatch) -> None:
    response = _app(monkeypatch).test_client().get("/sg/sub/v1/sg1_example?format=json")
    assert response.status_code == 200
    assert response.mimetype == "application/json"
    payload = response.get_json()
    assert payload["format"] == "sg-subscription"
    assert payload["version"] == 1
    assert payload["summary"] == {"devices": 2, "profiles_assigned": 6, "profiles_ready": 5}


def test_v3_preserves_route_names_and_auth_boundary(monkeypatch) -> None:
    app = _app(monkeypatch)
    rules = {rule.endpoint: rule.rule for rule in app.url_map.iter_rules()}
    assert rules[http.PUBLIC_ENDPOINT] == "/sg/sub/v1/<token>"
    assert rules[http.INFO_ENDPOINT] == "/api/clients/<int:client_id>/sg-subscription-v1"
    assert rules[http.QR_ENDPOINT] == "/clients/<int:client_id>/sg-subscription-v1/qr"
    assert should_skip_auth(http.PUBLIC_ENDPOINT) is True
    assert should_skip_auth(http.INFO_ENDPOINT) is False
    assert should_skip_auth(http.QR_ENDPOINT) is False
