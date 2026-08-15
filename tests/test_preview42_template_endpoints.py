from __future__ import annotations

import ast
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _registered_endpoints() -> set[str]:
    tree = ast.parse((ROOT / "app/main.py").read_text(encoding="utf-8"))
    endpoints: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            call = decorator if isinstance(decorator, ast.Call) else None
            target = call.func if call is not None else decorator
            if not (
                isinstance(target, ast.Attribute)
                and isinstance(target.value, ast.Name)
                and target.value.id == "app"
                and target.attr in {"get", "post", "route", "put", "delete", "patch"}
            ):
                continue
            endpoints.add(node.name)
            if call is not None:
                for keyword in call.keywords:
                    if (
                        keyword.arg == "endpoint"
                        and isinstance(keyword.value, ast.Constant)
                        and isinstance(keyword.value.value, str)
                    ):
                        endpoints.add(keyword.value.value)
    return endpoints


def test_every_static_url_for_target_exists() -> None:
    endpoints = _registered_endpoints()
    missing: list[str] = []
    for template in (ROOT / "app/web/templates").rglob("*.html"):
        body = template.read_text(encoding="utf-8")
        for endpoint in re.findall(r"url_for\(\s*['\"]([^'\"]+)", body):
            if endpoint != "static" and endpoint not in endpoints:
                missing.append(f"{template.relative_to(ROOT)} -> {endpoint}")
    assert not missing, "Unknown Flask endpoint(s): " + ", ".join(missing)


def test_routing_help_link_uses_real_endpoint() -> None:
    body = (ROOT / "app/web/templates/routing.html").read_text(encoding="utf-8")
    assert "url_for('help_index')" in body
    assert "url_for('help')" not in body
