from __future__ import annotations

import base64
from urllib.parse import unquote, urlsplit

from app.clients.repository import Client
from app.clients import sg_subscription as subscription


def _client() -> Client:
    return Client(id=41, name="Base64 Client", enabled=True, expires_at=None, awg_status="applied", xray_status="applied")


def test_base64_transport_contains_only_ready_uri_profiles_with_labels(monkeypatch) -> None:
    document = {
        "client": {"id": 41, "name": "Base64 Client"},
        "devices": [
            {
                "id": 1,
                "name": "Primary",
                "primary": True,
                "profiles": [
                    {"id": "xray_xhttp_reality", "name": "Reality", "format": "uri", "ready": True, "uri": "vless://u@host:443?q=1#old"},
                    {"id": "amneziawg", "name": "AmneziaWG 2.0", "format": "config", "ready": True, "config": "[Interface]\nPrivateKey=x\n"},
                    {"id": "tuic", "name": "TUIC v5", "format": "uri", "ready": False, "uri": "tuic://hidden@host:443"},
                ],
            },
            {
                "id": 2,
                "name": "Phone",
                "primary": False,
                "profiles": [
                    {"id": "mieru", "name": "Mieru", "format": "uri", "ready": True, "uri": "mierus://user@host:8443"},
                ],
            },
        ],
    }
    monkeypatch.setattr(subscription, "build_sg_subscription_document", lambda client: document)

    encoded = subscription.build_compatible_subscription_body(_client())
    decoded = base64.b64decode(encoded).decode("utf-8")
    lines = decoded.splitlines()

    assert decoded.endswith("\n")
    assert len(lines) == 2
    assert lines[0].startswith("vless://")
    assert lines[1].startswith("mierus://")
    assert unquote(urlsplit(lines[0]).fragment) == "Base64 Client · Reality"
    assert unquote(urlsplit(lines[1]).fragment) == "Base64 Client · Phone · Mieru"
    assert "AmneziaWG" not in decoded
    assert "tuic://" not in decoded
    assert "SG-CONFIG" not in decoded


def test_empty_ready_uri_set_encodes_to_empty_string(monkeypatch) -> None:
    monkeypatch.setattr(
        subscription,
        "build_sg_subscription_document",
        lambda client: {"client": {"name": "Base64 Client"}, "devices": []},
    )
    assert subscription.build_compatible_subscription_body(_client()) == ""


def test_awg3_profiles_are_independent_canonical_config_profiles() -> None:
    assert "amneziawg3" in subscription.canonical_profile_ids()
    assert "amneziawg31" in subscription.canonical_profile_ids()
