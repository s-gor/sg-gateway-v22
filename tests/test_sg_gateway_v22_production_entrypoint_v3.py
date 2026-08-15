from __future__ import annotations

import ast
import importlib
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PRODUCTION = ROOT / "app" / "production.py"


def test_production_entrypoint_registers_v3_module_only() -> None:
    text = PRODUCTION.read_text(encoding="utf-8")
    tree = ast.parse(text)
    imports = {
        (node.module, tuple(alias.name for alias in node.names))
        for node in tree.body
        if isinstance(node, ast.ImportFrom)
    }
    assert ("app.main", ("app",)) in imports
    assert ("app.clients.sg_subscription_http_v3", ("register_sg_subscription",)) in imports
    assert "from app.clients.sg_subscription_http_v2 import register_sg_subscription" not in text
    assert "from app.clients.sg_subscription_http import register_sg_subscription" not in text
    calls = [
        node for node in tree.body
        if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
        and node.value.func.id == "register_sg_subscription"
    ]
    assert len(calls) == 1


def test_importing_production_owns_endpoints_with_v3(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SG_GATEWAY_DATA_DIR", str(tmp_path / "data"))
    sys.modules.pop("app.production", None)
    production = importlib.import_module("app.production")
    app = production.app
    endpoints = [rule.endpoint for rule in app.url_map.iter_rules()]
    assert endpoints.count("sg_subscription_v1") == 1
    assert endpoints.count("sg_subscription_v1_info") == 1
    assert endpoints.count("sg_subscription_v1_qr") == 1
    assert app.view_functions["sg_subscription_v1"].__module__ == "app.clients.sg_subscription_http_v3"
