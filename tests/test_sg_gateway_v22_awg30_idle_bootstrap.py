from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_historical_awg3_bootstrap_entrypoint_performs_eol_cleanup() -> None:
    source = (ROOT / "app/maintenance/awg3_idle_bootstrap.py").read_text(
        encoding="utf-8"
    )

    assert "from app.maintenance.retire_legacy_awg import retire_legacy_awg" in source
    assert "return retire_legacy_awg()" in source
    assert "apply_awg3()" not in source
    assert "_ensure_server_secrets" not in source


def test_clean_install_verifies_retired_awg3_and_live_awg31() -> None:
    workflow = (ROOT / ".github/workflows/clean-install-awg3-smoke.yml").read_text(
        encoding="utf-8"
    )

    assert "Verify retired runtimes and live AWG31" in workflow
    assert "! sudo systemctl is-active --quiet sg-gateway-awg3.service" in workflow
    assert "sudo test ! -e /etc/amnezia/amneziawg/awg3.conf" in workflow
    assert "! sudo ip link show dev awg3" in workflow
    assert "sudo systemctl is-active --quiet sg-gateway-awg31.service" in workflow
    assert "sudo test -S /run/amneziawg/awg31.sock" in workflow
    assert 'awg show awg31 listen-port)" = "587"' in workflow


def test_seeded_admin_awg3_finalizer_is_compatibility_noop(tmp_path: Path) -> None:
    from app.maintenance import seeded_admin_awg3

    database = tmp_path / "sg-gateway.sqlite"
    marker = seeded_admin_awg3.mark_seeded_admin_pending(database)
    assert marker.exists()

    assert seeded_admin_awg3.ensure_seeded_admin_awg3(database=database) is False
    assert not marker.exists()


def test_seeded_admin_awg3_noop_without_database() -> None:
    from app.maintenance import seeded_admin_awg3

    assert seeded_admin_awg3.ensure_seeded_admin_awg3() is False


def test_stage3a_keeps_compatibility_finalizer_before_awg31_migration() -> None:
    stage3a = (ROOT / "app/maintenance/awg31_stage3a.py").read_text(
        encoding="utf-8"
    )

    finalize = "seeded_awg3_created = ensure_seeded_admin_awg3(database=database)"
    migrate = "result = installer.migrate(database=database)"
    assert finalize in stage3a
    assert migrate in stage3a
    assert stage3a.index(finalize) < stage3a.index(migrate)
