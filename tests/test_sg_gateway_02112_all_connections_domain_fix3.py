from __future__ import annotations

from pathlib import Path

from app.connections import public_endpoint
from app.connections.service import list_connections
from app.db import init_db


ROOT = Path(__file__).resolve().parents[1]
DOMAIN = "sgr.casacam.net"
IP = "18.196.189.75"


def test_public_endpoint_prefers_ready_https_domain(monkeypatch):
    monkeypatch.setenv("SG_GATEWAY_PUBLIC_ADDRESS", IP)
    monkeypatch.setattr(
        public_endpoint,
        "tls_overview",
        lambda: {"https_ready": True, "domain": DOMAIN},
    )

    assert public_endpoint.public_host("203.0.113.55") == DOMAIN


def test_public_endpoint_falls_back_to_current_destination_ip(monkeypatch):
    monkeypatch.setenv("SG_GATEWAY_PUBLIC_ADDRESS", IP)
    monkeypatch.setattr(
        public_endpoint,
        "tls_overview",
        lambda: {"https_ready": False, "domain": DOMAIN},
    )

    assert public_endpoint.public_host("old.example") == IP


def test_all_connection_summaries_use_same_public_domain(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SG_GATEWAY_PUBLIC_ADDRESS", IP)
    monkeypatch.setattr(
        public_endpoint,
        "tls_overview",
        lambda: {"https_ready": True, "domain": DOMAIN},
    )
    init_db()

    rows = list_connections()

    assert {item.name for item in rows} == {"amneziawg31", "xray", "mihomo"}
    assert all(item.public_host == DOMAIN for item in rows)
    assert all(DOMAIN in item.note for item in rows)
    assert all(IP not in item.note for item in rows)


def test_connections_and_exports_share_public_endpoint_policy():
    service = (ROOT / "app/connections/service.py").read_text(encoding="utf-8")
    exports = (ROOT / "app/clients/exports.py").read_text(encoding="utf-8")

    assert 'awg31 = _summary("amneziawg31", "AmneziaWG 3.1", counts)' in service
    assert 'return [awg31, xray, mihomo]' in service
    assert "WHERE engine NOT IN ('amneziawg', 'amneziawg3')" in service
    assert "from app.connections.public_endpoint import public_host, working_tls_domain" in exports
    assert "return public_host(*fallbacks)" in exports
