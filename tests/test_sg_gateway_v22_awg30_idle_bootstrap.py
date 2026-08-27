from __future__ import annotations

from pathlib import Path


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
