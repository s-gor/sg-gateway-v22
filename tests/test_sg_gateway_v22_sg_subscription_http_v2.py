from __future__ import annotations

from flask import Flask

from app.clients.repository import Client
from app.clients import sg_subscription_http_v2 as http
from app.security.auth import should_skip_auth


def _client() -> Client:
    return Client(id=31, name="HTTP v2", enabled=True, expires_at=None, awg_status="applied", xray_status="applied")


def _document() -> dict:
    return {
        "format": "sg-subscription",
        "version": 1,
        "scope": "client",
        "client": {"id": 31, "name": "HTTP v2"},
        "summary": {"devices": 2, "profiles_assigned": 5, "profiles_ready": 4},
        "devices": [],
    }


def _app(monkeypatch) -> Flask:
    client = _client()
    monkeypatch.setattr(http, "get_client_by_subscription_token", lambda token: client)
    monkeypatch.setattr(http, "build_sg_subscription_document", lambda item: _document())
    monkeypatch.setattr(http, "build_sg_subscription_text", lambda item: "# SG-SUBSCRIPTION/1\nvless://example\n")
    app = Flask(__name__)
    http.register_sg_subscription(app)
    http.register_sg_subscription(app)
    return app


def test_default_feed_is_backward_compatible_text_with_summary_headers(monkeypatch) -> None:
    response = _app(monkeypatch).test_client().get("/sg/sub/v1/sg1_example")
    assert response.status_code == 200
    assert response.mimetype == "text/plain"
    assert response.get_data(as_text=True) == "# SG-SUBSCRIPTION/1\nvless://example\n"
    assert response.headers["Cache-Control"] == "no-store, max-age=0"
    assert response.headers["X-SG-Subscription-Format"] == "sg-subscription"
    assert response.headers["X-SG-Subscription-Version"] == "1"
    assert response.headers["X-SG-Subscription-Devices"] == "2"
    assert response.headers["X-SG-Subscription-Profiles-Assigned"] == "5"
    assert response.headers["X-SG-Subscription-Profiles-Ready"] == "4"


def test_format_json_preserves_structured_v1_document(monkeypatch) -> None:
    response = _app(monkeypatch).test_client().get("/sg/sub/v1/sg1_example?format=json")
    assert response.status_code == 200
    assert response.mimetype == "application/json"
    payload = response.get_json()
    assert payload["format"] == "sg-subscription"
    assert payload["version"] == 1
    assert payload["summary"] == {"devices": 2, "profiles_assigned": 5, "profiles_ready": 4}


def test_v2_keeps_endpoint_names_auth_boundary_and_private_qr_info(monkeypatch) -> None:
    app = _app(monkeypatch)
    rules = {rule.endpoint: rule.rule for rule in app.url_map.iter_rules()}
    assert rules[http.PUBLIC_ENDPOINT] == "/sg/sub/v1/<token>"
    assert rules[http.INFO_ENDPOINT] == "/api/clients/<int:client_id>/sg-subscription-v1"
    assert rules[http.QR_ENDPOINT] == "/clients/<int:client_id>/sg-subscription-v1/qr"
    assert should_skip_auth(http.PUBLIC_ENDPOINT) is True
    assert should_skip_auth(http.INFO_ENDPOINT) is False
    assert should_skip_auth(http.QR_ENDPOINT) is False
