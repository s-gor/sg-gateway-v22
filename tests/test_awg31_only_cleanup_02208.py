from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_connections_page_exposes_only_awg31() -> None:
    body = _read("app/web/templates/connections.html")
    panel = _read("app/web/templates/_awg31_panel.html")
    base = _read("app/web/templates/base.html")

    assert '{% include "_awg31_panel.html" %}' in body
    for retired in (
        "UDP VPN · ТРИ ПОКОЛЕНИЯ",
        "AmneziaWG 2.0",
        "AmneziaWG 3.0",
        "AWG 2.0",
        "AWG 3.0",
        "awgd-card-v2",
        "awgd-card-v3",
        "update_amneziawg')",
        "update_amneziawg3')",
    ):
        assert retired not in body, retired

    assert "AmneziaWG 3.1" in body or "AmneziaWG 3.1" in panel
    assert "AWG2 и AWG3.0" not in panel
    assert "AWG2/3" not in base
    assert "AWG3.1" in base


def test_installer_master_has_22_stages_and_no_retired_runtime_stages() -> None:
    body = _read("install.sh")
    main = body[body.index("main() {") :]

    assert "TOTAL_STAGES=22" in body
    assert "· 22 этапа" in main
    assert 'run_stage 6 "Xray runtime" stage_xray_runtime' in main
    assert 'run_stage 9 "NaiveProxy runtime" stage_naiveproxy_runtime' in main
    assert 'run_stage 17 "Независимый профиль AWG31" run_awg31_stage3a_migration' in main
    assert 'run_stage 21 "Проверка NaiveProxy" verify_naiveproxy_install_contract' in main
    assert 'run_stage 22 "Финальный контракт 22.08" stage_final_contract' in main
    assert 'AmneziaWG 2 runtime' not in main
    assert 'AmneziaWG 3 runtime' not in main
    assert "22/22 · NaiveProxy включён в основной мастер" in main


def test_clean_seed_never_creates_retired_awg_connections_or_credentials() -> None:
    body = _read("app/install_seed.py")

    assert '_save("amneziawg",' not in body
    assert '_save("amneziawg3",' not in body
    assert "SG_SEED_AWG_PORT" not in body
    assert "SG_SEED_AWG_PUBLIC_KEY" not in body
    assert "amneziawg,mihomo" not in body
    assert "amneziawg31" in body


def test_awg31_migration_does_not_build_or_install_awg30_runtime() -> None:
    body = _read("app/maintenance/awg31_stage3a.py")

    assert "AWG3_TOOLS_FILE" not in body
    assert "AWG3_GO_FILE" not in body
    assert 'name="awg3"' not in body
    assert "self.layout.awg3_runtime" not in body
    assert "sg-gateway-awg3.service" not in body
    assert "AWG31_TOOLS_FILE" in body
    assert "AWG31_GO_FILE" in body


def test_installer_does_not_install_or_restore_retired_awg_units() -> None:
    body = _read("install.sh")

    assert 'install -m 0644 "$PREFIX/deploy/sg-gateway-awg.service"' not in body
    assert 'install -m 0644 "$PREFIX/deploy/sg-gateway-awg3.service"' not in body

    restore = body[body.index("restore_update_runtime_services()") : body.index("stage9_verify_nginx()")]
    assert "sg-gateway-awg.service" not in restore
    assert "sg-gateway-awg3.service" not in restore

    firewall = body[body.index("stage_firewall_and_network()") : body.index("systemctl_with_retry()")]
    assert '"${AWG_PORT}/udp"' not in firewall
    assert '"${AWG3_PORT}/udp"' not in firewall
