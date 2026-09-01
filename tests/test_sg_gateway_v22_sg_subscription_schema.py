from __future__ import annotations

from types import SimpleNamespace

from app.clients.repository import Client, Device
from app.clients import sg_subscription as subscription


def _client() -> Client:
    return Client(
        id=17,
        name="Schema test",
        enabled=True,
        expires_at=None,
        awg_status="applied",
        xray_status="applied",
    )


def _device(device_id: int, name: str, primary: bool) -> Device:
    return Device(
        id=device_id,
        client_id=17,
        name=name,
        enabled=True,
        expires_at=None,
        is_primary=primary,
        created_at="2026-08-16 00:00:00",
    )


def test_canonical_profile_ids_preserve_v1_order_with_independent_awg_profiles() -> None:
    assert subscription.canonical_profile_ids() == (
        "xray_reality_tcp",
        "xray_xhttp_reality",
        "xray_xhttp_tls",
        "xray_hysteria2",
        "amneziawg",
        "amneziawg3",
        "amneziawg31",
        "mieru",
        "anytls",
        "tuic",
        "naiveproxy",
    )
    assert "amneziawg3" in subscription.canonical_profile_ids()
    assert "amneziawg31" in subscription.canonical_profile_ids()
    assert subscription.canonical_profile_ids()[-1] == "naiveproxy"


def test_anytls_and_tuic_uris_are_canonicalized() -> None:
    anytls = subscription._canonical_uri(
        "anytls",
        "anytls://u:p@example.test:443/original?foo=drop&sni=one.example&insecure=0&sni=two.example#A",
    )
    assert anytls == "anytls://u:p@example.test:443/?sni=one.example&insecure=0#A"

    tuic = subscription._canonical_uri(
        "tuic",
        "tuic://id:pw@example.test:443/x?noise=drop&sni=t.example&alpn=h3&udp_relay_mode=native&congestion_control=bbr#T",
    )
    assert tuic == (
        "tuic://id:pw@example.test:443/?congestion_control=bbr&udp_relay_mode=native&alpn=h3&sni=t.example#T"
    )


def test_document_is_client_scoped_multi_device_and_counts_assigned_ready(monkeypatch) -> None:
    client = _client()
    primary = _device(101, "Primary", True)
    phone = _device(102, "Phone", False)
    monkeypatch.setattr(subscription, "list_devices", lambda client_id: [primary, phone])

    assigned = {
        101: ["xray_xhttp_reality", "mihomo"],
        102: ["amneziawg", "tuic"],
    }
    monkeypatch.setattr(
        subscription,
        "device_access_tokens",
        lambda device_id: assigned[device_id],
    )

    not_ready = {"tuic"}
    monkeypatch.setattr(
        subscription,
        "protocol_ready",
        lambda client, kind, device: kind not in not_ready,
    )

    exports = {
        "xray-xhttp-reality": "vless://example",
        "mieru": "mierus://example",
        "amneziawg": "[Interface]\nPrivateKey=x\n",
    }
    monkeypatch.setattr(
        subscription,
        "build_protocol_export",
        lambda client, kind, device: SimpleNamespace(
            body=exports.get(kind, ""),
            media_type="text/plain; charset=utf-8",
        ),
    )

    document = subscription.build_sg_subscription_document(client)

    assert document["format"] == "sg-subscription"
    assert document["version"] == 1
    assert document["scope"] == "client"
    assert document["client"]["id"] == 17
    assert document["summary"] == {
        "devices": 2,
        "profiles_assigned": 4,
        "profiles_ready": 3,
    }
    assert [item["id"] for item in document["devices"][0]["profiles"]] == [
        "xray_xhttp_reality",
        "mieru",
    ]
    assert [item["id"] for item in document["devices"][1]["profiles"]] == [
        "amneziawg",
        "tuic",
    ]
    assert document["devices"][1]["profiles"][1]["ready"] is False
    assert all(
        profile["id"] not in {"amneziawg3", "amneziawg31"}
        for device in document["devices"]
        for profile in device["profiles"]
    )
