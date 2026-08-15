from __future__ import annotations

from flask import Flask, render_template_string

from app.clients.repository import Client
from app.clients import sg_subscription_http_v4 as http
from app.security.auth import should_skip_auth


def _client() -> Client:
    return Client(id=61, name="HTTP v4", enabled=True, expires_at=None, awg_status="applied", xray_status="applied")


def _document() -> dict:
    return {
        "format": "sg-subscription",
        "version": 1,
        "scope": "client",
        "client": {"id": 61, "name": "HTTP v4"},
        "summary": {"devices": 2, "profiles_assigned": 7, "profiles_ready": 6},
        "devices": [],
    }


def _app(monkeypatch) -> Flask:
    client = _client()
    monkeypatch.setattr(http, "get_client_by_subscription_token", lambda token: client)
    monkeypatch.setattr(http, "get_client", lambda client_id: client if client_id == 61 else None)
    monkeypatch.setattr(http, "build_sg_subscription_url", lambda item: "https://vpn.example/sg/sub/v1/sg1_dual")
    monkeypatch.setattr(http, "build_sg_subscription_document", lambda item: _document())
    monkeypatch.setattr(http, "build_compatible_subscription_body", lambda item: "dmxlc3M6Ly9leGFtcGxlCg==")
    monkeypatch.setattr(http, "build_sg_subscription_text", lambda item: "# SG-SUBSCRIPTION/1\nvless://example\n")
    monkeypatch.setattr(http, "build_qr_svg", lambda value: f"<svg>{value}</svg>")
    app = Flask(__name__)
    http.register_sg_subscription(app)
    http.register_sg_subscription(app)
    return app


def test_v4_url_contract_and_info_aliases(monkeypatch) -> None:
    app = _app(monkeypatch)
    response = app.test_client().get("/api/clients/61/sg-subscription-v1")
    assert response.status_code == 200
    payload = response.get_json()
    universal = "https://vpn.example/sg/sub/v1/sg1_dual"
    native = universal + "?format=sg"
    assert payload["url"] == native
    assert payload["compat_url"] == universal
    assert payload["universal_url"] == universal
    assert payload["native_url"] == native
    assert payload["json_url"] == universal + "?format=json"


def test_v4_native_and_universal_qr_use_distinct_urls_and_stay_private(monkeypatch) -> None:
    app = _app(monkeypatch)
    native = app.test_client().get("/clients/61/sg-subscription-v1/qr")
    universal = app.test_client().get("/clients/61/sg-subscription-v1/qr/universal")
    assert native.status_code == 200
    assert universal.status_code == 200
    assert b"?format=sg" in native.data
    assert b"?format=sg" not in universal.data
    assert b"https://vpn.example/sg/sub/v1/sg1_dual" in universal.data
    assert should_skip_auth(http.PUBLIC_ENDPOINT) is True
    assert should_skip_auth(http.INFO_ENDPOINT) is False
    assert should_skip_auth(http.QR_ENDPOINT) is False
    assert should_skip_auth(http.UNIVERSAL_QR_ENDPOINT) is False


def test_v4_template_context_exposes_historical_and_explicit_dual_names(monkeypatch) -> None:
    app = _app(monkeypatch)
    client = _client()
    with app.test_request_context("/"):
        rendered = render_template_string(
            "{{ sg_subscription_url(client) }}|{{ sg_subscription_compat_url(client) }}|"
            "{{ sg_subscription_universal_url(client) }}|{{ sg_subscription_native_url(client) }}",
            client=client,
        )
    universal = "https://vpn.example/sg/sub/v1/sg1_dual"
    native = universal + "?format=sg"
    assert rendered == f"{native}|{universal}|{universal}|{native}"


def test_v4_preserves_three_feed_modes(monkeypatch) -> None:
    app = _app(monkeypatch)
    default = app.test_client().get("/sg/sub/v1/sg1_dual")
    sg = app.test_client().get("/sg/sub/v1/sg1_dual?format=sg")
    js = app.test_client().get("/sg/sub/v1/sg1_dual?format=json")
    assert default.get_data(as_text=True) == "dmxlc3M6Ly9leGFtcGxlCg=="
    assert sg.get_data(as_text=True) == "# SG-SUBSCRIPTION/1\nvless://example\n"
    assert js.get_json()["summary"]["profiles_ready"] == 6
