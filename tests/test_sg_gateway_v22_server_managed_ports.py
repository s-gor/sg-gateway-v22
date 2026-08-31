from pathlib import Path
from types import SimpleNamespace

from app.mihomo import service as mihomo_service
from app.xray import profiles as xray_profiles


ROOT = Path(__file__).resolve().parents[1]


def _xray_config() -> dict:
    return {
        "fingerprint": "firefox",
        "reality_tcp_enabled": True,
        "reality_tcp_port": 10443,
        "xhttp_reality_enabled": False,
        "xhttp_reality_port": 18444,
        "xhttp_reality_path": "/sg-xhttp-reality",
        "xhttp_reality_mode": "stream-one",
        "xhttp_tls_enabled": False,
        "xhttp_tls_port": 18445,
        "xhttp_tls_path": "/sg-xhttp-tls",
        "xhttp_tls_mode": "auto",
        "hysteria2_enabled": False,
        "hysteria2_port": 18446,
        "hysteria2_obfs_mode": "none",
        "hysteria2_obfs_password": "",
        "hysteria2_finalmask": {},
        "hysteria2_uri_scheme": "hysteria2",
    }


def test_xray_listener_ports_ignore_forged_form_values(monkeypatch) -> None:
    settings = SimpleNamespace(host="203.0.113.10", port=10443)
    monkeypatch.setattr(
        xray_profiles,
        "_config",
        lambda: (settings, _xray_config(), {"https_ready": True}),
    )

    prepared = xray_profiles._prepare(
        {
            "host": "203.0.113.10",
            "fingerprint": "firefox",
            "reality_tcp_enabled": "1",
            "reality_tcp_port": "20443",
            "xhttp_reality_port": "28444",
            "xhttp_reality_path": "/sg-xhttp-reality",
            "xhttp_reality_mode": "stream-one",
            "xhttp_tls_port": "28445",
            "xhttp_tls_path": "/sg-xhttp-tls",
            "xhttp_tls_mode": "auto",
            "hysteria2_port": "28446",
            "hysteria2_obfs_mode": "none",
        }
    )

    assert prepared.port == 10443
    assert prepared.config["reality_tcp_port"] == 10443
    assert prepared.config["xhttp_reality_port"] == 18444
    assert prepared.config["xhttp_tls_port"] == 18445
    assert prepared.config["hysteria2_port"] == 18446


def test_mihomo_listener_ports_ignore_forged_form_values(monkeypatch) -> None:
    current = SimpleNamespace(
        host="203.0.113.10",
        port=12099,
        config={
            "mieru_port": 12099,
            "anytls_port": 18443,
            "tuic_port": 20443,
            "mieru_transport": "TCP",
            "mieru_multiplexing": "MULTIPLEXING_LOW",
            "mieru_handshake": "HANDSHAKE_STANDARD",
            "mieru_user_hint_mandatory": True,
            "anytls_padding_scheme": "",
            "tuic_congestion_controller": "bbr",
            "tuic_udp_relay_mode": "native",
            "tuic_alpn": "h3",
        },
    )
    saved: dict = {}

    monkeypatch.setattr(
        mihomo_service,
        "get_connection_settings",
        lambda engine: current,
    )
    monkeypatch.setattr(
        mihomo_service,
        "_endpoint_metadata",
        lambda: {
            "host": "203.0.113.10",
            "public_ip": "203.0.113.10",
            "domain": "",
            "country_code": "unknown",
            "endpoint_source": "Текущий сервер",
            "country_source": "Страна не определена",
            "source_engine": "mihomo",
        },
    )

    def capture(engine: str, host: str, port: int, config: dict) -> bool:
        saved.update(engine=engine, host=host, port=port, config=dict(config))
        return True

    monkeypatch.setattr(mihomo_service, "update_connection_settings", capture)

    assert mihomo_service.save_settings(
        {
            "mieru_enabled": "1",
            "mieru_port": "22099",
            "mieru_transport": "TCP",
            "mieru_multiplexing": "MULTIPLEXING_LOW",
            "mieru_handshake": "HANDSHAKE_STANDARD",
            "mieru_user_hint_mandatory": "1",
            "anytls_port": "28443",
            "tuic_port": "30443",
            "tuic_congestion_controller": "bbr",
            "tuic_udp_relay_mode": "native",
            "tuic_alpn": "h3",
        }
    )

    assert saved["port"] == 12099
    assert saved["config"]["mieru_port"] == 12099
    assert saved["config"]["anytls_port"] == 18443
    assert saved["config"]["tuic_port"] == 20443


def test_connections_ui_has_no_editable_server_port_controls() -> None:
    template = (ROOT / "app/web/templates/connections.html").read_text(encoding="utf-8")
    mihomo = (ROOT / "app/web/templates/_mihomo_panel.html").read_text(encoding="utf-8")

    assert 'name="{{ profile.id }}_port"' not in template
    assert 'name="port" min="1" max="65535"' not in template
    for field in ("mieru_port", "anytls_port", "tuic_port"):
        assert f'name="{field}"' not in mihomo

    assert "Системный порт SG-Gateway" in template
    assert "Системный порт SG-Gateway" in mihomo
    assert "{{ profile.port }}" in template
    assert "{{ mihomo.settings.mieru_port }}" in mihomo
    assert "{{ mihomo.settings.anytls_port }}" in mihomo
    assert "{{ mihomo.settings.tuic_port }}" in mihomo


def test_real_user_controls_remain_available() -> None:
    template = (ROOT / "app/web/templates/connections.html").read_text(encoding="utf-8")
    mihomo = (ROOT / "app/web/templates/_mihomo_panel.html").read_text(encoding="utf-8")

    assert 'name="fingerprint"' in template
    assert 'name="server_name"' in template
    assert 'name="{{ profile.id }}_mode"' in template
    assert "XHTTP mode клиента" in template
    assert 'name="hysteria2_obfs_mode"' in template
    assert 'name="mieru_transport"' in mihomo
    assert 'name="tuic_congestion_controller"' in mihomo
