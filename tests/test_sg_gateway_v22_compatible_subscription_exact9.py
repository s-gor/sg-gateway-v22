from __future__ import annotations

import base64
import json

from app.clients.repository import Client
from app.clients import sg_subscription as subscription


EXPECTED = (
    "xray_reality_tcp",
    "xray_xhttp_reality",
    "xray_xhttp_tls",
    "xray_hysteria2",
    "amneziawg31",
    "mieru",
    "anytls",
    "tuic",
    "naiveproxy",
)


def _client() -> Client:
    return Client(id=41, name="Exact Nine", enabled=True, expires_at=None, awg_status="applied", xray_status="applied")


def test_compatible_subscription_contract_is_exactly_the_same_nine_profiles_as_sg(monkeypatch) -> None:
    assert subscription.compatible_profile_ids() == EXPECTED

    uri_profiles = [profile_id for profile_id in EXPECTED if profile_id != "amneziawg31"]
    profiles = [
        {
            "id": profile_id,
            "name": profile_id,
            "format": "uri",
            "ready": True,
            "uri": f"{('vless' if profile_id.startswith('xray_') else profile_id)}://ready-{profile_id}",
        }
        for profile_id in uri_profiles
    ]
    profiles.extend(
        [
            {
                "id": "amneziawg31",
                "name": "AmneziaWG 3.1",
                "format": "config",
                "ready": True,
                "config": "[Interface]\nPrivateKey=awg31\n",
            },
            {
                "id": "amneziawg",
                "name": "AmneziaWG 2.0",
                "format": "config",
                "ready": True,
                "config": "[Interface]\nPrivateKey=retired2\n",
            },
            {
                "id": "amneziawg3",
                "name": "AmneziaWG 3.0",
                "format": "config",
                "ready": True,
                "config": "[Interface]\nPrivateKey=retired3\n",
            },
        ]
    )
    document = {
        "client": {"id": 41, "name": "Exact Nine"},
        "devices": [{"id": 1, "name": "", "primary": True, "profiles": profiles}],
    }
    monkeypatch.setattr(subscription, "build_sg_subscription_document", lambda client: document)

    decoded = base64.b64decode(subscription.build_compatible_subscription_body(_client())).decode("utf-8")
    lines = decoded.splitlines()
    markers = [json.loads(line.removeprefix("# SG-CONFIG ")) for line in lines if line.startswith("# SG-CONFIG ")]

    assert len(lines) == 9
    assert len(markers) == 1
    assert markers[0]["profile"] == "amneziawg31"
    assert "AmneziaWG 2.0" not in decoded
    assert "AmneziaWG 3.0" not in decoded
    assert "retired2" not in decoded
    assert "retired3" not in decoded
