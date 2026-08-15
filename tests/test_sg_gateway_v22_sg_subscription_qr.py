from flask import Flask, render_template_string

from app.clients.repository import Client
from app.clients import sg_subscription_http as http
from app.clients.qr import ClientQrError
from app.security.auth import should_skip_auth


def _client() -> Client:
    return Client(
        id=7,
        name="QR test",
        enabled=True,
        expires_at=None,
        awg_status="applied",
        xray_status="applied",
    )


def test_qr_route_uses_client_wide_sg_v1_url_and_template_gets_same_url(monkeypatch) -> None:
    client = _client()
    expected = "https://vpn.example/sg/sub/v1/sg1_clientwide"
    monkeypatch.setattr(http, "get_client", lambda client_id: client if client_id == client.id else None)
    monkeypatch.setattr(http, "build_sg_subscription_url", lambda item: expected)
    monkeypatch.setattr(http, "build_qr_svg", lambda value: f"<svg>{value}</svg>")

    app = Flask(__name__)
    http.register_sg_subscription(app)
    http.register_sg_subscription(app)

    response = app.test_client().get(f"/clients/{client.id}/sg-subscription-v1/qr")
    assert response.status_code == 200
    assert response.mimetype == "image/svg+xml"
    assert expected.encode() in response.data

    with app.test_request_context("/"):
        rendered = render_template_string("{{ sg_subscription_url(client) }}", client=client)
    assert rendered == expected
    assert should_skip_auth(http.QR_ENDPOINT) is False


def test_qr_route_preserves_404_and_409_boundaries(monkeypatch) -> None:
    app = Flask(__name__)
    http.register_sg_subscription(app)
    client = _client()

    monkeypatch.setattr(http, "get_client", lambda client_id: None)
    assert app.test_client().get("/clients/999/sg-subscription-v1/qr").status_code == 404

    monkeypatch.setattr(http, "get_client", lambda client_id: client)
    monkeypatch.setattr(http, "build_sg_subscription_url", lambda item: "")
    assert app.test_client().get("/clients/7/sg-subscription-v1/qr").status_code == 409


def test_qr_capacity_error_is_normalized_to_409(monkeypatch) -> None:
    client = _client()
    monkeypatch.setattr(http, "get_client", lambda client_id: client)
    monkeypatch.setattr(http, "build_sg_subscription_url", lambda item: "https://vpn.example/sg/sub/v1/sg1_big")

    def fail_qr(value: str) -> str:
        raise ClientQrError("too large")

    monkeypatch.setattr(http, "build_qr_svg", fail_qr)
    app = Flask(__name__)
    http.register_sg_subscription(app)
    response = app.test_client().get("/clients/7/sg-subscription-v1/qr")
    assert response.status_code == 409
    assert response.mimetype == "text/plain"
    assert b"too large" in response.data
