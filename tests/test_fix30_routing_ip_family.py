from __future__ import annotations

import json
import os
import shutil
import subprocess
import zipfile
from pathlib import Path

from jinja2 import Environment

from app.routing import runtime as routing_runtime
from app.routing import templates as routing_templates
from app.routing import warp


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


def _fake_warp_outbound() -> dict:
    return {
        "tag": "warp",
        "protocol": "wireguard",
        "settings": {
            "secretKey": "test-secret",
            "address": ["172.16.0.2/32", "2606:4700:110:8::2/128"],
            "peers": [
                {
                    "publicKey": "test-public",
                    "endpoint": "162.159.192.1:2408",
                    "allowedIPs": ["0.0.0.0/0", "::/0"],
                }
            ],
            "noKernelTun": True,
        },
    }


def _enable_fake_warp(monkeypatch) -> None:
    monkeypatch.setattr(warp, "enabled", lambda: True)
    monkeypatch.setattr(warp, "family_capabilities", lambda: {"ipv4": True, "ipv6": True})
    monkeypatch.setattr(warp, "routing_family_capabilities", lambda: {"ipv4": True, "ipv6": True})
    monkeypatch.setattr(warp, "outbound", lambda require_enabled=True: _fake_warp_outbound())


def test_family_gates_are_force_and_fail_closed():
    direct4 = routing_runtime.family_gate_outbound("direct4", 4)
    direct6 = routing_runtime.family_gate_outbound("direct6", 6)
    warp6 = routing_runtime.family_gate_outbound("warp6", 6, proxy_tag="warp-core")

    assert direct4["settings"]["domainStrategy"] == "ForceIPv4"
    assert direct4["settings"]["finalRules"] == [
        {"action": "block", "ip": ["::/0"], "blockDelay": 0},
    ]
    assert direct6["settings"]["domainStrategy"] == "ForceIPv6"
    assert direct6["settings"]["finalRules"] == [
        {"action": "block", "ip": ["0.0.0.0/0"], "blockDelay": 0},
    ]
    assert "proxySettings" not in direct4
    assert warp6["proxySettings"] == {"tag": "warp-core"}


def test_managed_outbounds_have_four_family_exits_and_one_warp_core(monkeypatch):
    _enable_fake_warp(monkeypatch)
    outbounds = routing_runtime.build_managed_outbounds([])
    by_tag = {item["tag"]: item for item in outbounds}

    assert [item["tag"] for item in outbounds[:3]] == ["direct", "warp", "block"]
    assert {"direct4", "direct6", "warp4", "warp6", "warp-core"} <= set(by_tag)
    assert by_tag["warp-core"]["protocol"] == "wireguard"
    assert by_tag["warp4"]["settings"]["domainStrategy"] == "ForceIPv4"
    assert by_tag["warp6"]["settings"]["domainStrategy"] == "ForceIPv6"
    assert by_tag["warp4"]["proxySettings"] == {"tag": "warp-core"}
    assert by_tag["warp6"]["proxySettings"] == {"tag": "warp-core"}
    assert by_tag["direct"]["settings"]["domainStrategy"] == "ForceIPv4"
    assert by_tag["warp"]["settings"]["domainStrategy"] == "ForceIPv4"


def test_sanitizer_preserves_explicit_family_actions(monkeypatch):
    monkeypatch.setattr(routing_runtime, "routing_capabilities", _all_capabilities)
    _enable_fake_warp(monkeypatch)
    fragment = routing_runtime.sanitize_managed_fragment(
        {
            "routing": {
                "domainStrategy": "IPIfNonMatch",
                "rules": [
                    {"type": "field", "domain": ["domain:one.example"], "outboundTag": "direct4"},
                    {"type": "field", "domain": ["domain:two.example"], "outboundTag": "direct6"},
                    {"type": "field", "domain": ["domain:three.example"], "outboundTag": "warp4"},
                    {"type": "field", "domain": ["domain:four.example"], "outboundTag": "warp6"},
                    {"type": "field", "domain": ["domain:ads.example"], "outboundTag": "block"},
                ],
            }
        }
    )
    assert [item["outboundTag"] for item in fragment["routing"]["rules"]] == [
        "direct4", "direct6", "warp4", "warp6", "block"
    ]


def test_legacy_actions_remain_ipv4_only(monkeypatch):
    monkeypatch.setattr(routing_runtime, "routing_capabilities", _all_capabilities)
    _enable_fake_warp(monkeypatch)
    fragment = routing_runtime.sanitize_managed_fragment(
        {
            "routing": {
                "domainStrategy": "IPIfNonMatch",
                "rules": [
                    {"type": "field", "domain": ["domain:legacy-direct.example"], "outboundTag": "direct"},
                    {"type": "field", "domain": ["domain:legacy-warp.example"], "outboundTag": "warp"},
                ],
            }
        }
    )
    assert [item["outboundTag"] for item in fragment["routing"]["rules"]] == ["direct", "warp"]
    outbounds = routing_runtime.build_managed_outbounds([])
    by_tag = {item["tag"]: item for item in outbounds}
    assert by_tag["direct"]["settings"]["domainStrategy"] == "ForceIPv4"
    assert by_tag["warp"]["settings"]["domainStrategy"] == "ForceIPv4"


def test_smart_candidate_keeps_selected_family_and_explicit_catch_all(monkeypatch):
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
            "blocked_action": "warp6",
            "ads_action": "block",
            "default_action": "direct6",
            "custom_warp4_domains": "ipv4-only.example",
            "custom_warp6_domains": "ipv6-only.example",
        }
    )
    candidate = routing_templates._smart_build(state)
    tags = [
        item["xray_rule"]["outboundTag"]
        for item in candidate["rules"]
        if item.get("enabled") and item.get("xray_rule")
    ]
    assert candidate["ready"] is True
    assert "warp4" in tags
    assert "warp6" in tags
    assert "block" in tags
    assert tags[-1] == "direct6"
    assert candidate["rules"][-1]["xray_rule"]["network"] == "tcp,udp"


def test_smart_legacy_values_are_semantically_ipv4():
    assert routing_templates._canonical_family_action("direct") == "direct4"
    assert routing_templates._canonical_family_action("warp") == "warp4"
    assert routing_templates._actions_equivalent("direct", "direct4")
    assert routing_templates._actions_equivalent("warp", "warp4")


def test_warp_profile_reports_both_families():
    assert warp._profile_family_flags(
        {
            "addresses": ["172.16.0.2/32", "2606:4700:110:8::2/128"],
            "allowed_ips": ["0.0.0.0/0", "::/0"],
        }
    ) == {"ipv4": True, "ipv6": True}
    assert warp.routing_uses_warp({"routing": {"rules": [{"outboundTag": "warp6"}]}})


def test_routing_template_exposes_five_actions_and_parses():
    source = (ROOT / "app/web/templates/routing.html").read_text(encoding="utf-8")
    Environment().parse(source)
    for token in (
        'value="direct4"', 'value="direct6"', 'value="warp4"', 'value="warp6"', 'value="block"'
    ):
        assert token in source
    assert "автоматически не переключается" in source
    assert "Через SG-Gateway" in source
    assert "Через WARP" in source


def test_hostd_client_runtime_uses_family_routing_in_place(monkeypatch, tmp_path):
    import sg_hostd.client_runtime as client_runtime

    source = (ROOT / "hostd/sg_hostd/client_runtime.py").read_text(encoding="utf-8")
    assert "sanitize_managed_fragment(payload)" in source
    assert "build_managed_outbounds([])" in source
    assert "client_runtime_impl" not in source
    assert "FIX30_FAMILY_ROUTING_ADAPTER" not in source

    managed = tmp_path / "routing.json"
    managed.write_text(
        json.dumps(
            {
                "routing": {
                    "domainStrategy": "IPIfNonMatch",
                    "rules": [
                        {
                            "type": "field",
                            "domain": ["domain:ipv6.example"],
                            "outboundTag": "direct6",
                        }
                    ],
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(client_runtime, "ROUTING_MANAGED", managed)
    monkeypatch.setattr(routing_runtime, "routing_capabilities", _all_capabilities)
    loaded = client_runtime._load_managed_routing()
    assert loaded["rules"][0]["outboundTag"] == "direct6"


def test_bundled_xray_accepts_family_gate_schema(tmp_path):
    archive = ROOT / "vendor/cores/Xray-linux-64.zip"
    assert archive.is_file()
    with zipfile.ZipFile(archive) as bundle:
        member = next(
            name for name in bundle.namelist()
            if Path(name).name == "xray" and not name.endswith("/")
        )
        binary = tmp_path / "xray"
        with bundle.open(member) as source, binary.open("wb") as target:
            shutil.copyfileobj(source, target)
    binary.chmod(0o755)

    payload = {
        "log": {"loglevel": "warning"},
        "inbounds": [],
        "outbounds": [
            routing_runtime.family_gate_outbound("direct", 4),
            routing_runtime.family_gate_outbound("direct6", 6),
            {"tag": "warp-core", "protocol": "freedom"},
            routing_runtime.family_gate_outbound("warp4", 4, proxy_tag="warp-core"),
            routing_runtime.family_gate_outbound("warp6", 6, proxy_tag="warp-core"),
            {"tag": "block", "protocol": "blackhole"},
        ],
        "routing": {"domainStrategy": "AsIs", "rules": []},
    }
    config = tmp_path / "config.json"
    config.write_text(json.dumps(payload), encoding="utf-8")
    result = subprocess.run(
        [str(binary), "run", "-test", "-config", str(config)],
        capture_output=True,
        text=True,
        timeout=30,
        env=dict(os.environ),
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout



def test_warp_failed_health_disables_only_failed_routing_family(monkeypatch, tmp_path):
    state = tmp_path / "warp.json"
    monkeypatch.setenv("SG_GATEWAY_WARP_STATE_PATH", str(state))
    warp.save_state(
        enabled=True,
        profile_ready=True,
        profile={
            "addresses": ["172.16.0.2/32", "2606:4700:110:8::2/128"],
            "allowed_ips": ["0.0.0.0/0", "::/0"],
        },
        last_test={
            "checked_at": "2026-08-16T00:00:00+00:00",
            "ipv4": {"supported": True, "ok": True, "ip": "104.16.0.1"},
            "ipv6": {"supported": True, "ok": False, "message": "IPv6 test failed"},
        },
    )
    assert warp.family_capabilities() == {"ipv4": True, "ipv6": True}
    assert warp.routing_family_capabilities() == {"ipv4": True, "ipv6": False}
    monkeypatch.setattr(warp, "profile_ready", lambda: True)
    view = warp.overview()
    assert view["families"] == {"ipv4": True, "ipv6": True}
    assert view["routing_families"] == {"ipv4": True, "ipv6": False}
    assert view["ipv4_ready"] is True
    assert view["ipv6_ready"] is False


def test_warp_failed_family_remains_profile_capable_for_retest(monkeypatch, tmp_path):
    state = tmp_path / "warp.json"
    monkeypatch.setenv("SG_GATEWAY_WARP_STATE_PATH", str(state))
    warp.save_state(
        profile_ready=True,
        profile={
            "addresses": ["172.16.0.2/32", "2606:4700:110:8::2/128"],
            "allowed_ips": ["0.0.0.0/0", "::/0"],
        },
        last_test={
            "ipv4": {"supported": True, "ok": True},
            "ipv6": {"supported": True, "ok": False},
        },
    )
    assert warp.family_capabilities()["ipv6"] is True
    assert warp.routing_family_capabilities()["ipv6"] is False


def test_managed_outbounds_omit_failed_warp_family(monkeypatch):
    monkeypatch.setattr(warp, "enabled", lambda: True)
    monkeypatch.setattr(warp, "routing_family_capabilities", lambda: {"ipv4": True, "ipv6": False})
    monkeypatch.setattr(warp, "outbound", lambda require_enabled=True: _fake_warp_outbound())
    tags = [item["tag"] for item in routing_runtime.build_managed_outbounds([])]
    assert "warp4" in tags
    assert "warp6" not in tags
    assert "warp-core" in tags


def test_health_guard_rejects_only_failed_warp_family(monkeypatch, tmp_path):
    state = tmp_path / "warp.json"
    monkeypatch.setenv("SG_GATEWAY_WARP_STATE_PATH", str(state))
    monkeypatch.setattr(warp, "profile_ready", lambda: True)
    warp.save_state(
        enabled=True,
        profile_ready=True,
        profile={
            "addresses": ["172.16.0.2/32", "2606:4700:110:8::2/128"],
            "allowed_ips": ["0.0.0.0/0", "::/0"],
        },
        last_test={
            "ipv4": {"supported": True, "ok": True},
            "ipv6": {"supported": True, "ok": False},
        },
    )
    warp.ensure_routing_supported({"routing": {"rules": [{"outboundTag": "warp4"}]}})
    try:
        warp.ensure_routing_supported({"routing": {"rules": [{"outboundTag": "warp6"}]}})
    except warp.WarpError as exc:
        assert "WARP IPv6" in str(exc)
    else:
        raise AssertionError("failed WARP IPv6 must be rejected")


def test_outbounds_template_shows_separate_warp_family_health():
    source = (ROOT / "app/web/templates/outbounds.html").read_text(encoding="utf-8")
    Environment().parse(source)
    assert "WARP IPv4:" in source
    assert "WARP IPv6:" in source
    assert "warp.last_test.get('ipv4'" in source
    assert "warp.last_test.get('ipv6'" in source
