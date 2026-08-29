from __future__ import annotations

import base64
import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "app" / "clients" / "sg_subscription.py"


def _load_module(monkeypatch):
    exports = ModuleType("app.clients.exports")
    exports.build_protocol_export = lambda *_args, **_kwargs: None
    exports.protocol_ready = lambda *_args, **_kwargs: False

    repository = ModuleType("app.clients.repository")
    repository.Client = object
    repository.device_access_tokens = lambda _device_id: []
    repository.list_devices = lambda _client_id: []

    monkeypatch.setitem(sys.modules, "app.clients.exports", exports)
    monkeypatch.setitem(sys.modules, "app.clients.repository", repository)

    spec = importlib.util.spec_from_file_location("sg_subscription_device_name_test", SOURCE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _profile(uri: str) -> dict:
    return {
        "id": "xray_reality_tcp",
        "name": "VLESS Reality TCP",
        "format": "uri",
        "ready": True,
        "uri": uri,
    }


def _document() -> dict:
    return {
        "client": {"name": "Test9"},
        "summary": {"devices": 2, "profiles_assigned": 2, "profiles_ready": 2},
        "devices": [
            {
                "id": 7,
                "name": "",
                "primary": True,
                "enabled": True,
                "profiles": [_profile("vless://primary@example.test:443?security=reality")],
            },
            {
                "id": 8,
                "name": "Планшет",
                "primary": False,
                "enabled": True,
                "profiles": [_profile("vless://tablet@example.test:443?security=reality")],
            },
        ],
    }


def test_subscription_document_hides_primary_name_and_keeps_added_device_name(monkeypatch):
    module = _load_module(monkeypatch)
    module.list_devices = lambda _client_id: [
        SimpleNamespace(id=7, name="Старое основное имя", is_primary=True, enabled=True, expires_at=None),
        SimpleNamespace(id=8, name="Планшет", is_primary=False, enabled=True, expires_at=None),
    ]
    module.device_access_tokens = lambda _device_id: []

    client = SimpleNamespace(id=1, name="Test9", enabled=True, expires_at=None)
    document = module.build_sg_subscription_document(client)

    assert document["devices"][0]["name"] == ""
    assert document["devices"][1]["name"] == "Планшет"


def test_subscription_outputs_omit_primary_name_and_show_added_device_name(monkeypatch):
    module = _load_module(monkeypatch)
    module.build_sg_subscription_document = lambda _client: _document()
    client = SimpleNamespace(name="Test9")

    text = module.build_sg_subscription_text(client)
    decoded = base64.b64decode(module.build_compatible_subscription_body(client)).decode("utf-8")
    labels = {
        urlsplit(line).username: unquote(urlsplit(line).fragment)
        for line in decoded.splitlines()
        if line.startswith("vless://")
    }

    assert '"id":7,"name":"","primary":true' in text
    assert '"id":8,"name":"Планшет","primary":false' in text
    assert labels["primary"] == "Test9 · VLESS Reality TCP"
    assert labels["tablet"] == "Test9 · Планшет · VLESS Reality TCP"
    assert "Основное устройство" not in text
    assert "Основное устройство" not in decoded
