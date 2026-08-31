from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path


def test_production_entrypoint_registers_sg_infosec_after_public_routes():
    text = Path("app/production.py").read_text(encoding="utf-8")
    assert "from app.security.sg_infosec import register_sg_infosec" in text
    assert "register_sg_infosec(app)" in text
    assert text.index("register_sg_subscription(app)") < text.index("register_sg_infosec(app)")
    assert text.index("register_router_subscription(app)") < text.index("register_sg_infosec(app)")


class FakeProductionApp:
    def __init__(self):
        self.context_processors = []

    def context_processor(self, func):
        self.context_processors.append(func)
        return func


def test_production_import_registers_infosec_after_route_extensions(monkeypatch):
    calls = []
    app = FakeProductionApp()

    modules = {
        "app.clients.mieru_router_http": ("register_mieru_router_http", "mieru"),
        "app.clients.router_subscription_http": ("register_router_subscription", "router"),
        "app.clients.sg_subscription_http_v4": ("register_sg_subscription", "sg-subscription"),
        "app.system_disk_cleanup_http": ("register_system_disk_cleanup", "disk-cleanup"),
        "app.xray.xmux_http": ("register_xmux_http", "xmux"),
        "app.security.sg_infosec": ("register_sg_infosec", "infosec"),
    }
    for module_name, (function_name, label) in modules.items():
        module = types.ModuleType(module_name)
        setattr(module, function_name, lambda _app, value=label: calls.append(value))
        monkeypatch.setitem(sys.modules, module_name, module)

    main = types.ModuleType("app.main")
    main.app = app
    monkeypatch.setitem(sys.modules, "app.main", main)

    runtime = types.ModuleType("app.runtime_ui")
    runtime.runtime_engine_state = lambda: None
    monkeypatch.setitem(sys.modules, "app.runtime_ui", runtime)

    spec = importlib.util.spec_from_file_location(
        "isolated_production", Path("app/production.py")
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert calls == [
        "sg-subscription",
        "router",
        "mieru",
        "xmux",
        "disk-cleanup",
        "infosec",
    ]
