from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_awg30_is_not_supported_for_new_client_credentials() -> None:
    repository = (ROOT / "app/clients/repository.py").read_text(encoding="utf-8")
    retirement = (ROOT / "app/clients/retired_awg.py").read_text(encoding="utf-8")

    assert 'RETIRED_ENGINES = frozenset({"amneziawg", "amneziawg3"})' in retirement
    assert "repository.SUPPORTED_ENGINES = tuple(" in retirement
    assert "repository.RUNTIME_ENGINES = tuple(" in retirement
    assert "amneziawg31" in repository


def test_awg30_and_awg31_historical_units_keep_separate_runtime_contracts() -> None:
    awg30 = (ROOT / "deploy/sg-gateway-awg3.service").read_text(encoding="utf-8")
    awg31 = (ROOT / "deploy/sg-gateway-awg31.service").read_text(encoding="utf-8")

    for unit in (awg30, awg31):
        assert "Type=simple" in unit
        assert "Environment=WG_PROCESS_FOREGROUND=1" in unit
        assert "RuntimeDirectory=amneziawg" in unit
        assert "RuntimeDirectoryPreserve=yes" in unit


def test_clean_install_workflow_verifies_awg30_is_retired() -> None:
    workflow = (ROOT / ".github/workflows/clean-install-awg3-smoke.yml").read_text(
        encoding="utf-8"
    )

    assert "Run native clean installer" in workflow
    assert "Verify retired runtimes and live AWG31" in workflow
    assert "! sudo systemctl is-active --quiet sg-gateway-awg3.service" in workflow
    assert "sudo test ! -e /etc/amnezia/amneziawg/awg3.conf" in workflow
    assert "! sudo ip link show dev awg3" in workflow
    assert "sudo systemctl is-active --quiet sg-gateway-awg31.service" in workflow
    assert "sudo test -S /run/amneziawg/awg31.sock" in workflow
    assert 'awg show awg31 listen-port)" = "587"' in workflow
    assert 'create_client("ci-clean-awg3", "amneziawg3")' not in workflow


def test_dev_guard_retains_pinned_awg30_media_for_migration_compatibility() -> None:
    workflow = (ROOT / ".github/workflows/dev-02206-guard.yml").read_text(encoding="utf-8")

    focused = workflow.split("- name: Run focused dev-02206 regressions", 1)[1]
    focused = focused.split("- name: Run full panel test suite", 1)[0]

    assert 'TOOLS="vendor/cores/amneziawg-tools-3.0.20260805.tar.gz"' in focused
    assert 'GO="vendor/cores/amneziawg-go-linux-amd64-v3.0.0"' in focused
    assert 'EXPECTED_TOOLS_VERSION="3.0.20260805"' in focused
