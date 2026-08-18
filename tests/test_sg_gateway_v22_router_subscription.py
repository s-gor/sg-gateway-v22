from __future__ import annotations

import importlib
import sys
from pathlib import Path

from flask import Flask

from app.clients import router_subscription_http as http
from app.clients import router_subscription_store as store
from app.clients import sg_subscription as subscription
from app.clients.repository import Client, Device, get_client, get_device
from app.db import connect, init_db
from app.security.auth import should_skip_auth

ROOT = Path(__file__).resolve().parents[1]


def _client() -> Client:
    return Client(
        id=71,
        name="Router user",
        enabled=True,
        expires_at=None,
        awg_status="applied",
        xray_status="applied",
    )


def _device() -> Device:
    return Device(
        id=701,
        client_id=71,
        name="Home router",
        enabled=True,
        expires_at=None,
        is_primary=False,
        created_at="2026-08-18 00:00:00",
    )


def _document() -> dict:
    return {
        "format": "sg-router-subscription",
        "version": 1,
        "scope": "device",
        "client": {"id": 71, "name": "Router user"},
        "device": {"id": 701, "name": "Home router", "primary": False},
        "summary": {"profiles": 2},
        "profiles": [
            {"id": "xray_reality_tcp", "protocol": "vless", "type": "uri", "value": "vless://example"},
            {"id": "amneziawg", "protocol": "amneziawg", "type": "config", "value": "[Interface]\n"},
        ],
    }


def test_router_document_is_device_scoped_and_contains_only_ready_profiles(monkeypatch) -> None:
    source = {
        "devices": [
            {
                "id": 701,
                "name": "Home router",
                "primary": False,
                "enabled": True,
                "expires_at": None,
                "profiles": [
                    {
                        "id": "xray_reality_tcp",
                        "name": "VLESS Reality TCP",
                        "protocol": "vless",
                        "format": "uri",
                        "ready": True,
                        "uri": "vless://example",
                    },
                    {
                        "id": "tuic",
                        "name": "TUIC v5",
                        "protocol": "tuic",
                        "format": "uri",
                        "ready": False,
                    },
                    {
                        "id": "amneziawg",
                        "name": "AmneziaWG 2.0",
                        "protocol": "amneziawg",
                        "format": "config",
                        "ready": True,
                        "config": "[Interface]\n",
                    },
                ],
            },
            {"id": 702, "name": "Phone", "enabled": True, "profiles": []},
        ]
    }
    monkeypatch.setattr(subscription, "build_sg_subscription_document", lambda client: source)

    document = subscription.build_router_subscription_document(_client(), 701)

    assert document is not None
    assert document["format"] == "sg-router-subscription"
    assert document["version"] == 1
    assert document["scope"] == "device"
    assert document["device"]["id"] == 701
    assert document["summary"] == {"profiles": 2}
    assert [item["id"] for item in document["profiles"]] == ["xray_reality_tcp", "amneziawg"]
    assert document["profiles"][0]["type"] == "uri"
    assert document["profiles"][1]["type"] == "config"
    assert subscription.build_router_subscription_document(_client(), 999) is None


def test_router_token_is_stable_per_device_and_disabled_device_stops_resolving(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SG_GATEWAY_DATA_DIR", str(tmp_path / "data"))
    init_db()
    with connect() as connection:
        client_id = int(
            connection.execute(
                "INSERT INTO clients(name, enabled) VALUES ('Router user', 1)"
            ).lastrowid
        )
        device_id = int(
            connection.execute(
                "INSERT INTO devices(client_id, name, enabled, is_primary) VALUES (?, 'Home router', 1, 1)",
                (client_id,),
            ).lastrowid
        )

    first = store.ensure_router_subscription_token(client_id, device_id)
    second = store.ensure_router_subscription_token(client_id, device_id)
    assert first == second
    assert first.startswith("sgr1_")
    access = store.get_router_subscription_access(first)
    assert access is not None
    assert access[0] == get_client(client_id)
    assert access[1] == get_device(device_id, client_id)

    with connect() as connection:
        connection.execute("UPDATE devices SET enabled = 0 WHERE id = ?", (device_id,))
    assert store.get_router_subscription_access(first) is None


def test_router_url_uses_device_token_and_json_path(monkeypatch) -> None:
    monkeypatch.setattr(store, "ensure_router_subscription_token", lambda client_id, device_id: "sgr1_testtoken")
    monkeypatch.setattr(store, "subscription_base_url", lambda: "https://vpn.example")
    url = store.build_router_subscription_url(_client(), _device())
    assert url == "https://vpn.example/sg/router/v1/sgr1_testtoken.json"
    assert store.build_router_subscription_download_url(_client(), _device()) == url + "?download=1"


def test_router_http_feed_and_download_contract(monkeypatch) -> None:
    monkeypatch.setattr(http, "get_router_subscription_access", lambda token: (_client(), _device()))
    monkeypatch.setattr(http, "build_router_subscription_document", lambda client, device_id: _document())
    app = Flask(__name__)
    http.register_router_subscription(app)
    http.register_router_subscription(app)

    response = app.test_client().get("/sg/router/v1/sgr1_example.json")
    assert response.status_code == 200
    assert response.mimetype == "application/json"
    assert response.get_json()["summary"] == {"profiles": 2}
    assert response.headers["Cache-Control"] == "no-store, max-age=0"
    assert response.headers["X-SG-Router-Format"] == "sg-router-subscription"
    assert response.headers["X-SG-Router-Version"] == "1"
    assert response.headers["X-SG-Router-Profiles"] == "2"

    download = app.test_client().get("/sg/router/v1/sgr1_example.json?download=1")
    assert download.headers["Content-Disposition"] == (
        'attachment; filename="SG-Router-Router-user-Home-router.json"'
    )
    assert should_skip_auth(http.PUBLIC_ENDPOINT) is True


def test_router_ui_and_production_registration_are_source_native(monkeypatch, tmp_path) -> None:
    detail = (ROOT / "app/web/templates/client_detail.html").read_text(encoding="utf-8")
    assert detail.count("data-sg-router-subscription-v1") == 1
    assert "router_subscription_url(client, device)" in detail
    assert "Скопировать ссылку" in detail
    assert "Скачать JSON" in detail

    monkeypatch.setenv("SG_GATEWAY_DATA_DIR", str(tmp_path / "data"))
    sys.modules.pop("app.production", None)
    production = importlib.import_module("app.production")
    endpoints = [rule.endpoint for rule in production.app.url_map.iter_rules()]
    assert endpoints.count("router_subscription_v1") == 1
    production.app.jinja_env.get_template("client_detail.html")
