from __future__ import annotations

import ast
import importlib
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PRODUCTION = ROOT / "app" / "production.py"


def test_production_entrypoint_registers_v4_only_without_legacy_backup_http() -> None:
    text = PRODUCTION.read_text(encoding="utf-8")
    tree = ast.parse(text)
    imports = {
        (node.module, tuple(alias.name for alias in node.names))
        for node in tree.body
        if isinstance(node, ast.ImportFrom)
    }
    assert ("app.main", ("app",)) in imports
    assert ("app.clients.sg_subscription_http_v4", ("register_sg_subscription",)) in imports
    assert "sg_subscription_http_v3 import register_sg_subscription" not in text
    assert "sg_subscription_http_v2 import register_sg_subscription" not in text
    assert "full_backup_verify_http" not in text
    calls = [
        node for node in tree.body
        if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
        and node.value.func.id == "register_sg_subscription"
    ]
    assert len(calls) == 1


def test_importing_production_owns_dual_endpoints_with_v4(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SG_GATEWAY_DATA_DIR", str(tmp_path / "data"))
    sys.modules.pop("app.production", None)
    production = importlib.import_module("app.production")
    app = production.app
    endpoints = [rule.endpoint for rule in app.url_map.iter_rules()]
    assert endpoints.count("sg_subscription_v1") == 1
    assert endpoints.count("sg_subscription_v1_info") == 1
    assert endpoints.count("sg_subscription_v1_qr") == 1
    assert endpoints.count("sg_subscription_v1_universal_qr") == 1
    assert app.view_functions["sg_subscription_v1"].__module__ == "app.clients.sg_subscription_http_v4"
    with app.test_request_context("/"):
        context = {}
        for processor in app.template_context_processors[None]:
            context.update(processor())
    assert callable(context.get("sg_subscription_universal_url"))
    assert callable(context.get("sg_subscription_native_url"))
