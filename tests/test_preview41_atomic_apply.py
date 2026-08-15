from __future__ import annotations

import json
from pathlib import Path

from app.routing import geofiles, templates
from app.routing.geofiles import _report_payload, validate_pair
from app.routing.runtime import build_roscom_direct_block_fragment


def _varint(value: int) -> bytes:
    result = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            result.append(byte | 0x80)
        else:
            result.append(byte)
            return bytes(result)


def _field(number: int, payload: bytes) -> bytes:
    return _varint((number << 3) | 2) + _varint(len(payload)) + payload


def _geo_file(path: Path, categories: list[str]) -> None:
    entries = [_field(1, _field(1, category.encode())) for category in categories]
    path.write_bytes(b"".join(entries * 100))
    assert path.stat().st_size > 1024


def test_routing_apply_updates_live_config_and_rollback(tmp_path, monkeypatch):
    state = tmp_path / "routing-state"
    config = tmp_path / "config.json"
    managed = tmp_path / "managed.json"
    old_config = {
        "inbounds": [],
        "outbounds": [
            {"tag": "direct", "protocol": "freedom"},
            {"tag": "block", "protocol": "blackhole"},
        ],
        "routing": {
            "rules": [
                {"type": "field", "network": "tcp,udp", "outboundTag": "direct"}
            ]
        },
    }
    old_managed = {"routing": old_config["routing"]}
    config.write_text(json.dumps(old_config), encoding="utf-8")
    managed.write_text(json.dumps(old_managed), encoding="utf-8")
    monkeypatch.setenv("SG_GATEWAY_ROUTING_STATE_DIR", str(state))
    monkeypatch.setenv("SG_GATEWAY_XRAY_CONFIG", str(config))
    monkeypatch.setenv("SG_GATEWAY_ROUTING_MANAGED_PATH", str(managed))
    monkeypatch.setattr(templates, "xray_test_config", lambda *a, **k: ("ok", "accepted"))
    monkeypatch.setattr(templates, "service_is_active", lambda: False)

    fragment = {
        "routing": {
            "domainStrategy": "IPIfNonMatch",
            "rules": [
                {"type": "field", "domain": ["domain:ads.example"], "outboundTag": "block"},
                {"type": "field", "network": "tcp,udp", "outboundTag": "direct"},
            ],
        }
    }
    candidate = {
        "ready": True,
        "template_id": "test",
        "title": "Test",
        "managed_fragment": fragment,
        "rules": [],
    }
    templates._write_json(state / "candidate.json", candidate)
    result = templates.root_apply_candidate()
    assert result["ok"] is True
    assert json.loads(config.read_text())["routing"] == fragment["routing"]
    assert json.loads(managed.read_text()) == fragment

    restored = templates.root_rollback_latest()
    assert restored["ok"] is True
    assert json.loads(config.read_text()) == old_config
    restored_managed = json.loads(managed.read_text())
    assert restored_managed["routing"]["rules"] == old_managed["routing"]["rules"]
    assert restored_managed["routing"]["domainStrategy"] == "IPIfNonMatch"


def test_geofiles_apply_and_rollback_restore_pair_routing_and_config(tmp_path, monkeypatch):
    state = tmp_path / "geo-state"
    asset = tmp_path / "asset"
    asset.mkdir()
    config = tmp_path / "config.json"
    managed = tmp_path / "managed.json"
    old_geoip = asset / "geoip.dat"
    old_geosite = asset / "geosite.dat"
    _geo_file(old_geoip, ["private", "ru"])
    _geo_file(old_geosite, ["private", "category-ads-all"])
    old_config = {
        "inbounds": [],
        "outbounds": [
            {"tag": "direct", "protocol": "freedom"},
            {"tag": "block", "protocol": "blackhole"},
        ],
        "routing": {
            "rules": [
                {"type": "field", "network": "tcp,udp", "outboundTag": "direct"}
            ]
        },
    }
    old_managed = {"routing": old_config["routing"]}
    config.write_text(json.dumps(old_config), encoding="utf-8")
    managed.write_text(json.dumps(old_managed), encoding="utf-8")

    candidate = state / "candidate"
    candidate.mkdir(parents=True)
    _geo_file(candidate / "geoip.dat", ["direct", "private", "whitelist"])
    _geo_file(
        candidate / "geosite.dat",
        ["private", "whitelist", "category-ru", "category-ads"],
    )
    routing = build_roscom_direct_block_fragment(
        geosite_categories={"private", "whitelist", "category-ru", "category-ads"},
        geoip_categories={"direct", "private", "whitelist"},
        block_ads=True,
    )
    (candidate / "routing.json").write_text(json.dumps(routing), encoding="utf-8")
    report = validate_pair(
        candidate / "geoip.dat",
        candidate / "geosite.dat",
        "roscomvpn",
        "RoscomVPN",
    )
    report = geofiles.replace(
        report,
        family="roscomvpn",
        compatibility_mode="roscomvpn-direct-block",
        ready=True,
        xray_validation="ok",
        xray_message="accepted",
    )
    (candidate / "manifest.json").write_text(
        json.dumps(_report_payload(report)), encoding="utf-8"
    )

    monkeypatch.setenv("SG_GATEWAY_GEOFILES_STATE_DIR", str(state))
    monkeypatch.setenv("SG_GATEWAY_XRAY_ASSET_DIR", str(asset))
    monkeypatch.setenv("SG_GATEWAY_XRAY_CONFIG", str(config))
    monkeypatch.setenv("SG_GATEWAY_ROUTING_MANAGED_PATH", str(managed))
    # Production uses /run/sg-gateway/geofiles.lock, which is writable by the
    # privileged service on EC2.  GitHub Actions runs this unit test unprivileged,
    # so isolate only the lock file inside pytest's temporary directory.
    monkeypatch.setattr(geofiles, "GEOFILES_LOCK_PATH", tmp_path / "geofiles.lock")
    monkeypatch.setattr(geofiles, "xray_test_config", lambda *a, **k: ("ok", "accepted"))
    monkeypatch.setattr(geofiles, "service_is_active", lambda: False)
    monkeypatch.setattr(geofiles, "_sync_compatibility_asset_path", lambda *a, **k: None)

    old_geoip_hash = geofiles._sha256(old_geoip)
    result = geofiles.root_apply_candidate()
    assert result["ok"] is True
    assert geofiles._sha256(asset / "geoip.dat") == geofiles._sha256(candidate / "geoip.dat")
    assert json.loads(managed.read_text()) == routing
    assert json.loads(config.read_text())["routing"] == routing["routing"]

    rolled = geofiles.root_rollback_latest()
    assert rolled["ok"] is True
    assert geofiles._sha256(asset / "geoip.dat") == old_geoip_hash
    assert json.loads(managed.read_text()) == old_managed
    assert json.loads(config.read_text()) == old_config
