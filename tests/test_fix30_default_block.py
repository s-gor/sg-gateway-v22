from __future__ import annotations

from pathlib import Path

from jinja2 import Environment

from app.routing import templates as routing_templates


ROOT = Path(__file__).resolve().parents[1]


def _all_capabilities() -> dict[str, bool]:
    return {
        "direct4": True,
        "direct6": True,
        "warp4": True,
        "warp6": True,
        "block": True,
        "warp_enabled": True,
    }


def test_default_traffic_ui_exposes_block_action():
    source = (ROOT / "app/web/templates/routing.html").read_text(encoding="utf-8")
    Environment().parse(source)
    assert "action_group('default_action', smart.get('default_action', 'direct4'))" in source
    assert "action_group('default_action', smart.get('default_action', 'direct4'), True, False)" not in source


def test_default_traffic_block_builds_fail_closed_catch_all(monkeypatch):
    monkeypatch.setattr(
        routing_templates,
        "_available_categories",
        lambda: (
            {"private", "ru"},
            {"private", "russia-blocked", "category-ads-all", "category-ru", "tld-ru"},
        ),
    )
    monkeypatch.setattr(routing_templates, "routing_capabilities", _all_capabilities)
    state = routing_templates._smart_state_from_form(
        {
            "preset": "custom",
            "local_action": "direct4",
            "russia_scope": "none",
            "russia_action": "direct4",
            "blocked_action": "direct4",
            "ads_action": "direct4",
            "default_action": "block",
        }
    )
    assert state["default_action"] == "block"
    candidate = routing_templates._smart_build(state)
    assert candidate["ready"] is True
    final_rule = candidate["rules"][-1]
    assert final_rule["enabled"] is True
    assert final_rule["xray_rule"]["outboundTag"] == "block"
    assert final_rule["xray_rule"]["network"] == "tcp,udp"
