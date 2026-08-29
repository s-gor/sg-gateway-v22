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


def _document() -> dict:
    return {
        "client": {"name": "Test9"},
        "summary": {"devices": 1, "profiles_assigned": 1, "profiles_ready": 1},
        "devices": [
            {
                "id": 7,
                "name": "Телефон Test9",
                "primary": True,
                "enabled": True,
                "profiles": [
                    {
                        "id": "xray_reality_tcp",
                        "name": "VLESS Reality TCP",
                        "format": "uri",
                        "ready": True,
                        "uri": "vless://uuid@example.test:443?security=reality",
                    }
                ],
            }
        ],
    }


def test_primary_device_keeps_its_real_name_in_subscription_outputs(monkeypatch):
    module = _load_module(monkeypatch)
    module.build_sg_subscription_document = lambda _client: _document()
    client = SimpleNamespace(name="Test9")

    text = module.build_sg_subscription_text(client)
    decoded = base64.b64decode(module.build_compatible_subscription_body(client)).decode("utf-8")
    uri_line = next(line for line in decoded.splitlines() if line.startswith("vless://"))
    label = unquote(urlsplit(uri_line).fragment)

    assert '"name":"Телефон Test9"' in text
    assert label == "Test9 · Телефон Test9 · VLESS Reality TCP"
    assert "Основное устройство" not in text
    assert "Основное устройство" not in decoded
