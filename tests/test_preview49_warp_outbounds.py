from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.routing import runtime, warp


SAMPLE_PROFILE = """[Interface]
PrivateKey = private-secret-key
Address = 172.16.0.2/32, 2606:4700:110:8765::2/128
DNS = 1.1.1.1
MTU = 1280

[Peer]
PublicKey = public-peer-key
AllowedIPs = 0.0.0.0/0, ::/0
Endpoint = engage.cloudflareclient.com:2408
"""


def _env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    root = tmp_path / "warp"
    root.mkdir()
    profile = root / "wgcf-profile.conf"
    profile.write_text(SAMPLE_PROFILE, encoding="utf-8")
    monkeypatch.setenv("SG_GATEWAY_WARP_STATE_DIR", str(root))
    monkeypatch.setenv("SG_GATEWAY_WARP_STATE_PATH", str(tmp_path / "warp.json"))
    monkeypatch.setenv("SG_GATEWAY_XRAY_CONFIG", str(tmp_path / "config.json"))
    monkeypatch.setenv("SG_GATEWAY_ROUTING_MANAGED_PATH", str(tmp_path / "routing.json"))
    warp.save_state(
        enabled=True,
        profile_ready=True,
        profile=warp.scrubbed_profile(),
        wgcf_version=warp.WGCF_VERSION,
    )
    return profile


def test_warp_profile_becomes_native_xray_outbound(monkeypatch, tmp_path):
    _env(monkeypatch, tmp_path)
    outbound = warp.outbound()
    assert outbound["tag"] == "warp"
    assert outbound["protocol"] == "wireguard"
    assert outbound["settings"]["noKernelTun"] is True
    assert outbound["settings"]["mtu"] == 1280
    assert outbound["settings"]["peers"][0]["endpoint"] == "162.159.192.1:2408"
    assert outbound["settings"]["secretKey"] == "private-secret-key"


def test_public_overview_never_contains_private_key(monkeypatch, tmp_path):
    _env(monkeypatch, tmp_path)
    payload = warp.overview()
    serialized = json.dumps(payload)
    assert payload["enabled"] is True
    assert "private-secret-key" not in serialized
    assert "account_path" not in serialized


def test_build_full_config_has_direct_warp_block_in_safe_order(monkeypatch, tmp_path):
    _env(monkeypatch, tmp_path)
    fragment = {
        "routing": {
            "domainStrategy": "IPIfNonMatch",
            "rules": [
                {"type": "field", "domain": ["domain:example.com"], "outboundTag": "warp"}
            ],
        }
    }
    config = runtime.build_full_config(fragment, base_config={"inbounds": [], "outbounds": []})
    assert [item["tag"] for item in config["outbounds"][:3]] == ["direct", "warp", "block"]
    assert config["routing"]["rules"][0]["outboundTag"] == "warp"


def test_warp_rule_is_rejected_when_warp_disabled(monkeypatch, tmp_path):
    _env(monkeypatch, tmp_path)
    warp.save_state(enabled=False, profile_ready=True, profile=warp.scrubbed_profile())
    with pytest.raises(runtime.RoutingRuntimeError, match="WARP"):
        runtime.sanitize_managed_fragment(
            {"routing": {"rules": [{"type": "field", "network": "tcp", "outboundTag": "warp"}]}}
        )



def test_loading_active_warp_rules_is_fail_closed(monkeypatch, tmp_path):
    _env(monkeypatch, tmp_path)
    warp.save_state(enabled=False, profile_ready=True, profile=warp.scrubbed_profile())
    runtime.managed_routing_path().write_text(
        json.dumps({"routing": {"rules": [{"type": "field", "network": "tcp", "outboundTag": "warp"}]}}),
        encoding="utf-8",
    )
    with pytest.raises(runtime.RoutingRuntimeError, match="WARP"):
        runtime.load_managed_fragment()

def test_hostd_whitelist_contains_all_warp_actions():
    from hostd.sg_hostd import privileged_runtime
    from hostd.sg_hostd import commands

    actions = {f"warp.{name}" for name in ("install", "recreate", "enable", "disable", "remove", "test", "export_json")}
    assert actions.issubset(privileged_runtime._ACTIONS)
    assert actions.issubset(commands._COMMANDS)


def test_warp_management_is_on_outbounds_and_routing_only_assigns_it():
    routing_source = Path("app/web/templates/routing.html").read_text(encoding="utf-8")
    outbounds_source = Path("app/web/templates/outbounds.html").read_text(encoding="utf-8")
    base_source = Path("app/web/templates/base.html").read_text(encoding="utf-8")

    assert 'data-r096-tab="warp"' not in routing_source
    assert 'data-r096-panel="warp"' not in routing_source
    assert "Ресурсы, заблокированные в РФ через WARP" in routing_source
    assert "Весь интернет через WARP" in routing_source
    assert "url_for('outbounds')" in routing_source
    assert "Создать WARP" not in routing_source

    assert "System outbounds" in outbounds_source
    assert "WARP Outbound" in outbounds_source
    assert "Создать выход <code>warp</code>" in outbounds_source
    assert "Маршрутизация настраивается отдельно" in outbounds_source
    assert "outbounds_warp_create" in outbounds_source
    create_form = outbounds_source.split("outbounds_warp_create", 1)[1].split("</form>", 1)[0]
    assert "data-sg-confirm" not in create_form
    assert "data-sg-confirm" in outbounds_source  # destructive actions only
    assert "Custom outbounds" in outbounds_source
    assert "fake" not in outbounds_source.lower()

    assert "url_for('outbounds')" in base_source
    assert "sg-outbounds-v49.css" not in base_source
    assert "static_asset('sg-ui-outbounds-v22-08.css')" in outbounds_source
    for source in (routing_source, outbounds_source):
        assert "confirm(" not in source
        assert "alert(" not in source
        assert "prompt(" not in source


def test_warp_secrets_are_not_world_readable_in_installer():
    source = Path("install.sh").read_text(encoding="utf-8")
    assert "secure_warp_secrets" in source
    assert 'chmod 0700 "$DATA_DIR/warp"' in source
    assert 'find "$DATA_DIR/warp" -type f -exec chmod 0600' in source
