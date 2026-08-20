from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
HOSTD = ROOT / "hostd"
if str(HOSTD) not in sys.path:
    sys.path.insert(0, str(HOSTD))

from sg_hostd import restore_hardening_patch, restore_service_health_patch


def _restore_module(events: list[str]) -> ModuleType:
    module = ModuleType("restore_health_test")

    def original(full) -> None:
        events.append("panel-health")

    module._local_panel_health = original
    return module


def test_restore_health_requires_panel_then_active_hostd() -> None:
    events: list[str] = []
    restore = _restore_module(events)
    restore_service_health_patch.install(restore)

    def probe(command, timeout=0):
        events.append("hostd-health")
        assert command == [
            "systemctl",
            "is-active",
            "--quiet",
            "sg-hostd.service",
        ]
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    restore._local_panel_health(SimpleNamespace(_probe=probe))

    assert events == ["panel-health", "hostd-health"]


def test_restore_health_fails_when_hostd_is_not_active() -> None:
    events: list[str] = []
    restore = _restore_module(events)
    restore_service_health_patch.install(restore)
    full = SimpleNamespace(
        _probe=lambda command, timeout=0: SimpleNamespace(
            returncode=3,
            stdout="inactive\n",
            stderr="",
        )
    )

    with pytest.raises(RuntimeError, match="hostd is not active"):
        restore._local_panel_health(full)

    assert events == ["panel-health"]


def test_package_installs_service_health_after_restore_hardening() -> None:
    source = (ROOT / "hostd/sg_hostd/__init__.py").read_text(encoding="utf-8")
    assert "restore_service_health_patch" in source
    assert source.index("install_restore(full_backup_runtime)") < source.index(
        "install_service_health(restore_hardening_patch)"
    )
    assert restore_hardening_patch._local_panel_health.__module__ == (
        "sg_hostd.restore_service_health_patch"
    )
