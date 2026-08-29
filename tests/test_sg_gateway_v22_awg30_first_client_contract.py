from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _awg3_input_tags(source: str) -> list[str]:
    return re.findall(
        r'<input\s+[^>]*name="protocols"[^>]*value="amneziawg3"[^>]*>',
        source,
        flags=re.S,
    )


def test_awg30_remains_submit_capable_in_client_create_and_edit_dialogs() -> None:
    create_source = (ROOT / "app/web/templates/clients.html").read_text(encoding="utf-8")
    edit_source = (ROOT / "app/web/templates/_client_edit_dialogs.html").read_text(encoding="utf-8")

    create_tags = _awg3_input_tags(create_source)
    edit_tags = _awg3_input_tags(edit_source)

    assert len(create_tags) == 1
    assert len(edit_tags) == 2
    for tag in create_tags + edit_tags:
        assert "disabled" not in tag

    # The removed browser-side readiness gate must not leave an undefined
    # Jinja variable behind in the client-detail include.
    assert "awg3_runtime" not in edit_source

    # Runtime provisioning remains the authoritative fail-closed check and
    # returns a precise recovery message if a real installation is incomplete.
    provisioning = (ROOT / "app/engines/provisioning.py").read_text(encoding="utf-8")
    assert "def _require_awg3_runtime()" in provisioning
    assert "AWG3 требует восстановления" in provisioning


def test_awg30_and_awg31_preserve_their_shared_runtime_directory() -> None:
    awg30 = (ROOT / "deploy/sg-gateway-awg3.service").read_text(encoding="utf-8")
    awg31 = (ROOT / "deploy/sg-gateway-awg31.service").read_text(encoding="utf-8")

    for unit in (awg30, awg31):
        assert "Type=simple" in unit
        assert "Environment=WG_PROCESS_FOREGROUND=1" in unit
        assert "RuntimeDirectory=amneziawg" in unit
        assert "RuntimeDirectoryPreserve=yes" in unit


def test_clean_install_workflow_creates_a_real_awg30_client() -> None:
    workflow = (ROOT / ".github/workflows/clean-install-awg3-smoke.yml").read_text(
        encoding="utf-8"
    )

    assert "Run native clean installer" in workflow
    assert 'create_client("ci-clean-awg3", "amneziawg3")' in workflow
    assert "apply_clients_runtime()" in workflow
    assert "systemctl is-active --quiet sg-gateway-awg3.service" in workflow
    assert "systemctl is-active --quiet sg-gateway-awg31.service" in workflow
    assert "test -S /run/amneziawg/awg3.sock" in workflow
    assert "test -S /run/amneziawg/awg31.sock" in workflow
    assert 'awg show awg3 listen-port)" = "586"' in workflow
    assert 'awg show awg31 listen-port)" = "587"' in workflow


def test_dev_guard_builds_the_exact_awg30_runtime_used_by_clean_install() -> None:
    workflow = (ROOT / ".github/workflows/dev-02206-guard.yml").read_text(encoding="utf-8")

    focused = workflow.split("- name: Run focused dev-02206 regressions", 1)[1]
    focused = focused.split("- name: Run full panel test suite", 1)[0]

    assert 'TOOLS="vendor/cores/amneziawg-tools-3.0.20260805.tar.gz"' in focused
    assert 'GO="vendor/cores/amneziawg-go-linux-amd64-v3.0.0"' in focused
    assert 'EXPECTED_TOOLS_VERSION="3.0.20260805"' in focused
    assert "if [[ -f vendor/cores/amneziawg-tools-3.1.20260812.tar.gz ]]" not in focused
