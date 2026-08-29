from __future__ import annotations

import base64
import json
from urllib.parse import unquote, urlsplit

from app.clients.repository import Client
from app.clients import sg_subscription as subscription


def _client() -> Client:
    return Client(id=23, name="Compat Client", enabled=True, expires_at=None, awg_status="applied", xray_status="applied")


def _document() -> dict:
    return {
        "format": "sg-subscription",
        "version": 1,
        "scope": "client",
        "client": {"id": 23, "name": "Compat Client"},
        "summary": {"devices": 2, "profiles_assigned": 4, "profiles_ready": 3},
        "devices": [
            {
                "id": 101, "name": "Primary", "primary": True, "enabled": True,
                "profiles": [
                    {"id": "xray_xhttp_reality", "name": "VLESS XHTTP Reality", "format": "uri", "ready": True, "uri": "vless://uuid@example.test:443?security=reality#old"},
                    {"id": "amneziawg", "name": "AmneziaWG 2.0", "format": "config", "ready": True, "config": "[Interface]\nPrivateKey = test\n"},
                ],
            },
            {
                "id": 102, "name": "Phone", "primary": False, "enabled": True,
                "profiles": [
                    {"id": "mieru", "name": "Mieru", "format": "uri", "ready": True, "uri": "mierus://user@example.test:443"},
                    {"id": "tuic", "name": "TUIC v5", "format": "uri", "ready": False},
                ],
            },
        ],
    }


def test_text_envelope_preserves_v1_headers_devices_ready_uris_and_awg2_config(monkeypatch) -> None:
    monkeypatch.setattr(subscription, "build_sg_subscription_document", lambda client: _document())
    text = subscription.build_sg_subscription_text(_client())
    lines = text.splitlines()
    assert text.endswith("\n")
    assert lines[:6] == [
        "# SG-SUBSCRIPTION/1", "# scope=client", "# client=Compat Client",
        "# devices=2", "# profiles-assigned=4", "# profiles-ready=3",
    ]
    devices = [json.loads(line.removeprefix("# SG-DEVICE ")) for line in lines if line.startswith("# SG-DEVICE ")]
    assert devices[0] == {"id": 101, "name": "", "primary": True, "enabled": True}
    assert devices[1] == {"id": 102, "name": "Phone", "primary": False, "enabled": True}
    uris = [line for line in lines if line.startswith(("vless://", "mierus://"))]
    assert len(uris) == 2
    assert unquote(urlsplit(uris[0]).fragment) == "Compat Client · VLESS XHTTP Reality"
    assert unquote(urlsplit(uris[1]).fragment) == "Compat Client · Phone · Mieru"
    assert not any("tuic://" in line for line in lines)
    markers = [json.loads(line.removeprefix("# SG-CONFIG ")) for line in lines if line.startswith("# SG-CONFIG ")]
    assert len(markers) == 1
    assert markers[0]["profile"] == "amneziawg"
    assert markers[0]["device_id"] == 101
    assert markers[0]["device"] == ""
    padded = markers[0]["data"] + "=" * (-len(markers[0]["data"]) % 4)
    assert base64.urlsafe_b64decode(padded).decode() == "[Interface]\nPrivateKey = test\n"


def test_fragment_replacement_and_awg_profile_order() -> None:
    value = subscription._with_fragment("vless://u@host:443?q=1#old", "Новая метка")
    assert urlsplit(value).query == "q=1"
    assert unquote(urlsplit(value).fragment) == "Новая метка"
    assert subscription._with_fragment("plain-text", "ignored") == "plain-text"
    assert subscription.canonical_profile_ids() == (
        "xray_reality_tcp", "xray_xhttp_reality", "xray_xhttp_tls", "xray_hysteria2",
        "amneziawg", "amneziawg3", "amneziawg31", "mieru", "anytls", "tuic",
    )
