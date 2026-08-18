from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_02204_version_identity_and_manifest_are_consistent() -> None:
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    build_id = (ROOT / "BUILD-ID").read_text(encoding="utf-8").strip()
    manifest = json.loads((ROOT / "release-manifest.json").read_text(encoding="utf-8"))
    assert version == "0.1.0-022.04"
    assert build_id == "MAIN-02204"
    assert manifest["version"] == version
    assert manifest["rebuild_target"] == version
    assert manifest["next_development_line"] == "0.1.0-022.05"
    assert manifest["rebuild_policy"]["baseline"] == "0.1.0-021.12"
    assert manifest["status"] == "STABLE"


def test_02204_manifest_describes_real_dual_stack_routing_and_manual_warp() -> None:
    manifest = json.loads((ROOT / "release-manifest.json").read_text(encoding="utf-8"))
    assert manifest["dual_stack"]["ipv6_absence_is_nonfatal"] is True
    assert manifest["dual_stack"]["ipv6_only_vps"] == "deferred"
    assert manifest["routing_ui"]["real_outbounds"] == ["direct4", "direct6", "warp4", "warp6", "block"]
    assert manifest["routing_ui"]["family_fallback"] is False
    assert manifest["routing_ui"]["default_traffic_block_supported"] is True
    assert manifest["warp"]["automatic_on_full_install"] is False
    assert manifest["warp"]["family_gates"] == ["warp4", "warp6"]
    assert manifest["warp"]["health_gates_routing"] is True
    assert "sg-gateway-awg3" in manifest["services"]


def test_02204_full_uninstall_removes_awg3_userspace_runtime() -> None:
    body = (ROOT / "deploy/full-uninstall-ubuntu.sh").read_text(encoding="utf-8")
    assert "sg-gateway-awg3.service" in body
    assert "ip link delete awg3" in body
    assert "/var/run/amneziawg/awg3.sock" in body
    assert "/etc/systemd/system/sg-gateway-awg3.service" in body


def test_02204_publication_document_is_present_and_covers_release_contract() -> None:
    body = (ROOT / "PUBLICATION-02204.md").read_text(encoding="utf-8")
    for marker in (
        "Dual Stack IPv4 + IPv6", "AWG3 userspace", "WARP", "Family Routing",
        "Non-destructive updater", "Hysteria2 Gecko", "XMUX", "SG subscription",
        "Low-resolution", "551 passed",
    ):
        assert marker in body
