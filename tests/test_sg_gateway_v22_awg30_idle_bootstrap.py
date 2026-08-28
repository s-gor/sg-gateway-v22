from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]


def test_awg30_apply_bootstraps_an_empty_server_runtime() -> None:
    source = (ROOT / "hostd/sg_hostd/awg3_runtime.py").read_text(encoding="utf-8")
    apply_body = source.split("def apply_awg3()", 1)[1]

    # A clean installation has no AWG3 peers yet. That state must still create
    # the independent server key/config and start UDP 586, exactly as AWG31
    # already does. The old early return left the panel forever at
    # "Готов к первому запуску" and deferred server bootstrap to the first
    # client transaction.
    assert "Нет активных клиентов AWG3" not in apply_body
    assert "_ensure_server_secrets()" in apply_body
    assert "_render(rows, secrets)" in apply_body
    assert '["systemctl", "restart", AWG3_SERVICE]' in apply_body


def test_clean_install_checks_awg30_before_creating_any_client() -> None:
    workflow = (ROOT / ".github/workflows/clean-install-awg3-smoke.yml").read_text(
        encoding="utf-8"
    )

    bootstrap_step = "Verify initialized AWG3 before any client"
    create_step = "Create and apply first AWG3 client"
    assert bootstrap_step in workflow
    assert workflow.index(bootstrap_step) < workflow.index(create_step)

    bootstrap = workflow.split(f"- name: {bootstrap_step}", 1)[1]
    bootstrap = bootstrap.split(f"- name: {create_step}", 1)[0]
    assert "systemctl is-active --quiet sg-gateway-awg3.service" in bootstrap
    assert "test -S /run/amneziawg/awg3.sock" in bootstrap
    assert "ip link show dev awg3" in bootstrap
    assert 'awg show awg3 listen-port)" = "586"' in bootstrap
    assert "SG_GATEWAY_AWG3_PUBLIC_KEY" in bootstrap


def test_clean_seed_requests_all_six_no_certificate_profiles(monkeypatch) -> None:
    from app import install_seed

    settings = {
        "xray": SimpleNamespace(host="", port=443, config={}),
        "amneziawg": SimpleNamespace(host="", port=585, config={}),
        "amneziawg3": SimpleNamespace(host="", port=586, config={}),
        "mihomo": SimpleNamespace(host="", port=2099, config={}),
    }
    environment = {
        "SG_UPDATE_MODE": "0",
        "SG_SEED_PUBLIC_ADDRESS": "203.0.113.10",
        "SG_GATEWAY_COUNTRY_CODE": "fr",
        "SG_SEED_VLESS_ENCRYPTION": "mlkem768-test",
        "SG_SEED_XRAY_PUBLIC_KEY": "xray-public-test",
        "SG_SEED_XRAY_SHORT_ID": "0123456789abcdef",
        "SG_SEED_AWG_PUBLIC_KEY": "awg-public-test",
        "SG_SEED_XRAY_PORT": "443",
        "SG_SEED_AWG_PORT": "585",
        "SG_SEED_REALITY_SNI": "www.bing.com",
        "SG_SEED_REALITY_TARGET": "www.bing.com:443",
        "SG_SEED_CREATE_ADMIN": "1",
    }
    for name, value in environment.items():
        monkeypatch.setenv(name, value)

    created: dict[str, str] = {}
    monkeypatch.setattr(install_seed, "init_db", lambda: None)
    monkeypatch.setattr(
        install_seed,
        "get_connection_settings",
        lambda engine: settings[engine],
    )
    monkeypatch.setattr(
        install_seed,
        "update_connection_settings",
        lambda engine, host, port, config: True,
    )
    monkeypatch.setattr(
        install_seed,
        "_synchronize_xray_credentials",
        lambda **kwargs: 0,
    )
    monkeypatch.setattr(install_seed, "count_clients", lambda: 0)

    def capture_client(name: str, requested: str) -> int:
        created["name"] = name
        created["requested"] = requested
        return 1

    monkeypatch.setattr(install_seed, "create_client", capture_client)

    install_seed.seed_or_migrate()

    assert created["name"] == "sg-admin"
    requested = set(created["requested"].split(","))
    assert requested == {
        "xray_reality_tcp",
        "xray_xhttp_reality",
        "amneziawg",
        "amneziawg3",
        "mihomo",
        "sgclient",
    }
    assert "amneziawg31" not in requested
