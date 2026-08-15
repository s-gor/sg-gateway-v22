from __future__ import annotations

import json
from pathlib import Path

from app.routing.runtime import default_routing, load_managed_fragment
from sg_hostd import client_runtime


def test_hostd_reads_managed_direct_block_rules(tmp_path, monkeypatch):
    path = tmp_path / "routing.json"
    path.write_text(
        json.dumps(
            {
                "routing": {
                    "domainStrategy": "IPIfNonMatch",
                    "rules": [
                        {
                            "type": "field",
                            "domain": ["domain:ads.example"],
                            "outboundTag": "block",
                        },
                        {
                            "type": "field",
                            "network": "tcp,udp",
                            "outboundTag": "direct",
                        },
                    ],
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(client_runtime, "ROUTING_MANAGED", path)
    routing = client_runtime._load_managed_routing()
    assert routing["rules"][0]["outboundTag"] == "block"
    assert routing["rules"][-1]["outboundTag"] == "direct"


def test_legacy_preview40_proxy_fragment_falls_back_to_direct(tmp_path, monkeypatch):
    path = tmp_path / "routing.json"
    path.write_text(
        json.dumps(
            {
                "routing": {
                    "rules": [
                        {
                            "type": "field",
                            "network": "tcp,udp",
                            "outboundTag": "xray",
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(client_runtime, "ROUTING_MANAGED", path)
    routing = client_runtime._load_managed_routing()
    assert routing == default_routing()["routing"]


def test_country_database_is_separate_from_routing_geofiles():
    source = Path("app/connections/geoip_country.py").read_text(encoding="utf-8")
    assert "/opt/sg-gateway/assets/geoip/sg-country-geoip.dat" in source
    country = Path("assets/geoip/sg-country-geoip.dat")
    assert country.is_file()
    assert country.stat().st_size > 1_000_000


def test_default_routing_uses_implicit_direct_fallback(tmp_path, monkeypatch):
    path = tmp_path / "missing.json"
    monkeypatch.setattr(client_runtime, "ROUTING_MANAGED", path)
    routing = client_runtime._load_managed_routing()
    assert routing == {"domainStrategy": "AsIs", "rules": []}
