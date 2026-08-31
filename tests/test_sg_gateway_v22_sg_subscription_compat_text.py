from __future__ import annotations

import base64
import json
from urllib.parse import unquote, urlsplit

from app.clients.repository import Client
from app.clients import sg_subscription as subscription


_AWG_PROFILES = (
    ("amneziawg", "AmneziaWG 2.0", "[Interface]\r\nPrivateKey = awg2\r\n"),
    ("amneziawg3", "AmneziaWG 3.0", "[Interface]\nPrivateKey = awg3\n"),
    ("amneziawg31", "AmneziaWG 3.1", "[Interface]\nPrivateKey = awg31\n"),
)


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


def _awg_contract_document() -> dict:
    def config_profiles(prefix: str) -> list[dict]:
        return [
            {
                "id": profile_id,
                "name": profile_name,
                "format": "config",
                "ready": True,
                "config": f"{prefix}:{config}",
            }
            for profile_id, profile_name, config in _AWG_PROFILES
        ]

    return {
        "format": "sg-subscription",
        "version": 1,
        "scope": "client",
        "client": {"id": 23, "name": "sg-admin"},
        "summary": {"devices": 2, "profiles_assigned": 8, "profiles_ready": 8},
        "devices": [
            {
                "id": 101,
                "name": "Primary",
                "primary": True,
                "enabled": True,
                "profiles": [
                    {
                        "id": "xray_xhttp_reality",
                        "name": "VLESS XHTTP Reality",
                        "format": "uri",
                        "ready": True,
                        "uri": "vless://uuid@example.test:443?security=reality#old",
                    },
                    *config_profiles("primary"),
                ],
            },
            {
                "id": 102,
                "name": "Phone",
                "primary": False,
                "enabled": True,
                "profiles": [
                    {
                        "id": "mieru",
                        "name": "Mieru",
                        "format": "uri",
                        "ready": True,
                        "uri": "mierus://user@example.test:443",
                    },
                    *config_profiles("phone"),
                ],
            },
        ],
    }


def _fix24_visible_awg_names(text: str) -> list[str]:
    lines = [line.strip() for line in text.splitlines()]
    client_line = next((line for line in lines if line.lower().startswith("# client=")), "")
    client_name = client_line[len("# client="):].strip() if client_line else ""
    result = []
    for line in lines:
        if not line.startswith("# SG-CONFIG "):
            continue
        root = json.loads(line.removeprefix("# SG-CONFIG "))
        raw_device = root.get("device")
        device_name = raw_device.strip() if isinstance(raw_device, str) else ""
        primary = root.get("primary") is True
        device_label = "Основное устройство" if primary else (device_name or "Устройство")
        profile_label = str(root.get("name") or root.get("profile") or "").strip()
        display_name = " · ".join(
            value for value in (client_name, device_label, profile_label) if value
        )
        suffix = f" · {profile_label}"
        result.append(display_name[:-len(suffix)] if display_name.endswith(suffix) else display_name)
    return result


def _decode_config(marker: dict) -> str:
    encoded = marker["data"]
    return base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)).decode("utf-8")


def test_text_envelope_preserves_v1_headers_devices_ready_uris_and_awg2_config(monkeypatch) -> None:
    monkeypatch.setattr(subscription, "build_sg_subscription_document", lambda client: _document())
    text = subscription.build_sg_subscription_text(_client())
    lines = text.splitlines()
    assert text.endswith("\n")
    assert lines[:6] == [
        "# SG-SUBSCRIPTION/1", "# scope=client", "# client-name=Compat Client",
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
    assert markers[0]["device"] == "Compat Client"
    assert "primary" not in markers[0]
    padded = markers[0]["data"] + "=" * (-len(markers[0]["data"]) % 4)
    assert base64.urlsafe_b64decode(padded).decode() == "[Interface]\nPrivateKey = test\n"


def test_awg_markers_render_primary_and_named_devices_without_client_fallback_labels(monkeypatch) -> None:
    monkeypatch.setattr(subscription, "build_sg_subscription_document", lambda client: _awg_contract_document())
    client = Client(id=23, name="sg-admin", enabled=True, expires_at=None, awg_status="applied", xray_status="applied")
    text = subscription.build_sg_subscription_text(client)
    lines = text.splitlines()

    assert "# client=sg-admin" not in lines
    assert "# client-name=sg-admin" in lines

    markers = [json.loads(line.removeprefix("# SG-CONFIG ")) for line in lines if line.startswith("# SG-CONFIG ")]
    assert len(markers) == 6
    assert [marker["profile"] for marker in markers] == [
        "amneziawg", "amneziawg3", "amneziawg31",
        "amneziawg", "amneziawg3", "amneziawg31",
    ]
    assert [marker["device_id"] for marker in markers] == [101, 101, 101, 102, 102, 102]
    assert [marker["name"] for marker in markers] == [name for _, name, _ in _AWG_PROFILES] * 2
    assert [marker["device"] for marker in markers] == ["sg-admin"] * 3 + ["sg-admin · Phone"] * 3
    assert all(marker["encoding"] == "base64url" for marker in markers)
    assert all("primary" not in marker for marker in markers)
    assert [_decode_config(marker) for marker in markers] == [
        *(f"primary:{config}" for _, _, config in _AWG_PROFILES),
        *(f"phone:{config}" for _, _, config in _AWG_PROFILES),
    ]

    assert _fix24_visible_awg_names(text) == ["sg-admin"] * 3 + ["sg-admin · Phone"] * 3

    uris = [line for line in lines if line.startswith(("vless://", "mierus://"))]
    assert unquote(urlsplit(uris[0]).fragment) == "sg-admin · VLESS XHTTP Reality"
    assert unquote(urlsplit(uris[1]).fragment) == "sg-admin · Phone · Mieru"


def test_fragment_replacement_and_awg_profile_order() -> None:
    value = subscription._with_fragment("vless://u@host:443?q=1#old", "Новая метка")
    assert urlsplit(value).query == "q=1"
    assert unquote(urlsplit(value).fragment) == "Новая метка"
    assert subscription._with_fragment("plain-text", "ignored") == "plain-text"
    assert subscription.canonical_profile_ids() == (
        "xray_reality_tcp", "xray_xhttp_reality", "xray_xhttp_tls", "xray_hysteria2",
        "amneziawg", "amneziawg3", "amneziawg31", "mieru", "anytls", "tuic",
    )
