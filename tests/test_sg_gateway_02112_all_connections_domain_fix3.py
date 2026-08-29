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

    assert {item.name for item in rows} == {"amneziawg", "amneziawg3", "xray", "mihomo"}
    assert all(item.public_host == DOMAIN for item in rows)
    assert all(DOMAIN in item.note for item in rows)
    assert all(IP not in item.note for item in rows)


def test_connections_page_uses_public_host_for_every_engine():
    page = (ROOT / "app/web/templates/connections.html").read_text(encoding="utf-8")
    mihomo_panel = (ROOT / "app/web/templates/_mihomo_panel.html").read_text(encoding="utf-8")
    service = (ROOT / "app/connections/service.py").read_text(encoding="utf-8")
    exports = (ROOT / "app/clients/exports.py").read_text(encoding="utf-8")

    assert "SG_GATEWAY_02112_ALL_CONNECTIONS_DOMAIN_FIX3" in service
    assert "awg_public_host = public_host(awg.host)" in service
    assert "awg3_public_host = public_host(awg3.host)" in service
    assert "xray_public_host = public_host(xray.host)" in service
    assert "mihomo_public_host = public_host(mihomo.host)" in service

    assert "<strong>{{ xray_public_host }}</strong>" in page
    assert 'name="host" value="{{ xray_public_host }}"' in page
    assert (
        "<strong>{{ awg_public_host }}:{{ awg_settings.port }} · "
        "DNS {{ awg_dns.dns }}</strong>"
    ) in page
    assert 'name="host" value="{{ awg_public_host }}"' in page
    assert (
        "<strong>{{ awg3_public_host }}:{{ awg3_settings.port }} · "
        "DNS {{ awg_dns.dns }}</strong>"
    ) in page
    assert 'name="host" value="{{ awg3_public_host }}"' in page
    assert "AWG2: {{ awg_public_host }}:{{ awg_settings.port }}" in page
    assert "AWG3: {{ awg3_public_host }}:{{ awg3_settings.port }}" in page
    assert "Xray Reality: {{ xray_public_host }}:{{ xray_settings.port }}" in page
    assert "Mihomo: {{ mihomo_public_host }}" in page
    assert "<strong>{{ mihomo_public_host or 'Не определён' }}</strong>" in mihomo_panel

    # Client exports use the same central endpoint policy, so every connection
    # and every downloadable/QR/subscription payload follows one domain-first rule.
    assert "from app.connections.public_endpoint import public_host, working_tls_domain" in exports
    assert "return public_host(*fallbacks)" in exports
