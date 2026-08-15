from __future__ import annotations

from pathlib import Path

from app.routing import geofiles
from app.routing.geofiles import GeoFileReport, GeoPairReport
from app.routing.runtime import extract_geo_references


def _report(family: str, geoip: tuple[str, ...], geosite: tuple[str, ...]) -> GeoPairReport:
    return GeoPairReport(
        source_id="test",
        source_label="Test",
        checked_at="2026-07-29T00:00:00+00:00",
        valid=True,
        message="ok",
        geoip=GeoFileReport("geoip", "/tmp/geoip.dat", 2048, "a" * 64, geoip, True, "ok"),
        geosite=GeoFileReport("geosite", "/tmp/geosite.dat", 2048, "b" * 64, geosite, True, "ok"),
        family=family,
        ready=True,
    )


def test_roscom_to_runetfreedom_does_not_reuse_old_roscom_managed_rules(monkeypatch):
    old_roscom = {
        "routing": {
            "rules": [
                {"type": "field", "ip": ["geoip:direct", "geoip:whitelist"], "outboundTag": "direct"},
                {"type": "field", "domain": ["geosite:whitelist"], "outboundTag": "direct"},
            ]
        }
    }
    monkeypatch.setattr(geofiles, "_routing_state", lambda: {})
    monkeypatch.setattr(geofiles, "_active_family", lambda: "roscomvpn")
    monkeypatch.setattr(geofiles, "load_managed_fragment", lambda: old_roscom)

    fragment, plan = geofiles._plan_routing_for_candidate(
        _report("runetfreedom", ("private", "ru"), ("private", "category-ru", "tld-ru")),
        block_ads=False,
        block_windows_telemetry=False,
        block_torrent=False,
    )
    ip_refs, site_refs = extract_geo_references(fragment)
    assert "direct" not in ip_refs
    assert "whitelist" not in ip_refs
    assert "whitelist" not in site_refs
    assert plan["previous_family"] == "roscomvpn"
    assert plan["policy_source"] == "legacy-family-transition"
    assert plan["blockers"] == []


def test_user_rule_is_preserved_and_blocks_when_candidate_category_is_missing(monkeypatch):
    monkeypatch.setattr(
        geofiles,
        "_routing_state",
        lambda: {
            "smart": {
                "preset": "custom",
                "russia_scope": "none",
                "blocked_action": "direct",
                "ads_action": "direct",
                "default_action": "direct",
                "custom_direct_domains": ["geosite:my-private-list"],
                "custom_direct_ips": [],
                "custom_block_domains": [],
                "custom_block_ips": [],
                "custom_warp_domains": [],
                "custom_warp_ips": [],
            }
        },
    )
    monkeypatch.setattr(geofiles, "_active_family", lambda: "roscomvpn")

    fragment, plan = geofiles._plan_routing_for_candidate(
        _report("runetfreedom", ("private", "ru"), ("private", "category-ru", "tld-ru")),
        block_ads=False,
        block_windows_telemetry=False,
        block_torrent=False,
    )
    domains = [
        value
        for rule in fragment["routing"]["rules"]
        for value in rule.get("domain", [])
    ]
    assert "geosite:my-private-list" in domains
    assert "Пользовательские правила Direct → geosite:my-private-list" in plan["blockers"]
    assert plan["user_rule_count"] == 1


def test_runetfreedom_to_roscomvpn_rebuilds_roscom_family_rules(monkeypatch):
    monkeypatch.setattr(geofiles, "_routing_state", lambda: {})
    monkeypatch.setattr(geofiles, "_active_family", lambda: "runetfreedom")
    report = _report(
        "roscomvpn",
        ("private", "direct", "whitelist"),
        ("private", "whitelist", "category-ru", "category-ads"),
    )
    fragment, plan = geofiles._plan_routing_for_candidate(
        report,
        block_ads=True,
        block_windows_telemetry=False,
        block_torrent=False,
    )
    ip_refs, site_refs = extract_geo_references(fragment)
    assert "direct" in ip_refs or "whitelist" in ip_refs
    assert "whitelist" in site_refs
    assert "category-ads" in site_refs
    assert plan["policy_source"] == "roscomvpn-family"
    assert plan["preset"] == "roscomvpn-direct-block"


def test_hostd_clean_install_has_directory_level_xray_asset_write_access():
    root = Path(__file__).resolve().parents[1]
    unit = (root / "hostd/systemd/sg-hostd.service").read_text(encoding="utf-8")
    install = (root / "install.sh").read_text(encoding="utf-8")
    assert "ProtectSystem=strict" in unit
    assert "ReadWritePaths=-/run/sg-gateway -/usr/local/share/xray" in unit
    assert "-/usr/local/share/xray" in install
    assert "geoip.dat.tmp-" not in unit
    assert "geosite.dat.tmp-" not in unit
