from __future__ import annotations

import json
from pathlib import Path

from app.routing import geofiles
from app.routing.runtime import (
    build_full_config,
    build_roscom_direct_block_fragment,
    extract_geo_references,
    sanitize_managed_fragment,
)


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
    entries = []
    for category in categories:
        entry = _field(1, category.encode())
        entries.append(_field(1, entry))
    payload = b"".join(entries * 80)
    path.write_bytes(payload)
    assert path.stat().st_size > 1024


def test_direct_block_fragment_rejects_fake_proxy():
    fragment = sanitize_managed_fragment(
        {
            "routing": {
                "rules": [
                    {"type": "field", "domain": ["domain:example.com"], "outboundTag": "block"},
                    {"type": "field", "network": "tcp,udp", "outboundTag": "direct"},
                ]
            }
        }
    )
    assert {rule["outboundTag"] for rule in fragment["routing"]["rules"]} == {"direct", "block"}


def test_roscom_fragment_is_direct_block_only():
    fragment = build_roscom_direct_block_fragment(
        geosite_categories={
            "private", "whitelist", "category-ru", "category-ads", "win-spy", "torrent"
        },
        geoip_categories={"private", "whitelist", "direct"},
        block_ads=True,
        block_windows_telemetry=True,
        block_torrent=True,
    )
    tags = [rule["outboundTag"] for rule in fragment["routing"]["rules"]]
    assert set(tags) == {"direct", "block"}
    assert not any(rule.get("network") == "tcp,udp" for rule in fragment["routing"]["rules"])
    assert not any(tag in {"vpn", "proxy", "xray"} for tag in tags)


def test_roscom_candidate_replaces_incompatible_active_categories(tmp_path, monkeypatch):
    geoip = tmp_path / "roscom-geoip.dat"
    geosite = tmp_path / "roscom-geosite.dat"
    _geo_file(geoip, ["direct", "private", "whitelist"])
    _geo_file(
        geosite,
        ["category-ru", "category-ads", "private", "whitelist", "win-spy", "torrent"],
    )

    state = tmp_path / "state"
    config = tmp_path / "config.json"
    managed = tmp_path / "managed.json"
    assets = tmp_path / "assets"
    assets.mkdir()
    config.write_text(
        json.dumps(
            {
                "inbounds": [],
                "outbounds": [
                    {"tag": "direct", "protocol": "freedom"},
                    {"tag": "block", "protocol": "blackhole"},
                ],
                "routing": {
                    "rules": [
                        {"type": "field", "domain": ["geosite:google"], "outboundTag": "direct"}
                    ]
                },
            }
        ),
        encoding="utf-8",
    )
    managed.write_text(
        json.dumps(
            {
                "routing": {
                    "rules": [
                        {"type": "field", "domain": ["geosite:google"], "outboundTag": "direct"},
                        {"type": "field", "network": "tcp,udp", "outboundTag": "direct"},
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("SG_GATEWAY_GEOFILES_STATE_DIR", str(state))
    monkeypatch.setenv("SG_GATEWAY_XRAY_CONFIG", str(config))
    monkeypatch.setenv("SG_GATEWAY_ROUTING_MANAGED_PATH", str(managed))
    monkeypatch.setenv("SG_GATEWAY_XRAY_ASSET_DIR", str(assets))
    monkeypatch.setattr(geofiles, "_find_xray", lambda: None)
    monkeypatch.setattr(geofiles, "log_operation", lambda *args, **kwargs: None)

    report = geofiles.stage_pair(
        "local",
        local_geoip=str(geoip),
        local_geosite=str(geosite),
        block_ads=True,
    )
    assert report.family == "roscomvpn"
    assert report.ready is True
    assert "geosite:google" in report.missing_active_categories
    assert report.compatibility_mode == "roscomvpn-direct-block"
    candidate_routing = json.loads((state / "candidate" / "routing.json").read_text())
    ip_refs, site_refs = extract_geo_references(candidate_routing)
    assert "google" not in site_refs
    assert "category-ads" in site_refs
    assert {rule["outboundTag"] for rule in candidate_routing["routing"]["rules"]} <= {"direct", "block"}


def test_full_config_uses_real_direct_and_block_outbounds():
    fragment = build_roscom_direct_block_fragment(
        geosite_categories={"private", "whitelist", "category-ru"},
        geoip_categories={"private", "whitelist", "direct"},
    )
    config = build_full_config(fragment, base_config={"inbounds": [], "outbounds": []})
    tags = {item["tag"] for item in config["outbounds"]}
    assert {"direct", "block"} <= tags
    assert {rule["outboundTag"] for rule in config["routing"]["rules"]} <= {"direct", "block"}
