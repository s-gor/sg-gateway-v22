from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


MODULE_PATH = (
    Path(__file__).parents[1]
    / "hostd"
    / "sg_hostd"
    / "naiveproxy_listener_patch.py"
)
SPEC = importlib.util.spec_from_file_location(
    "naiveproxy_apply_readiness_test", MODULE_PATH
)
listener_patch = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(listener_patch)


def _runtime(*, initially_active: bool, listener_after_apply: bool):
    calls: list[tuple[str, ...]] = []
    state = {"started": initially_active}
    service_pid = 321

    def run(command, timeout=10):
        command = tuple(command)
        calls.append(command)
        if command[:3] == ("ss", "-H", "-ltnp"):
            if state["started"] and listener_after_apply:
                stdout = (
                    "LISTEN 0 4096 0.0.0.0:8447 0.0.0.0:* "
                    f'users:(("caddy",pid={service_pid},fd=3))\n'
                )
            else:
                stdout = ""
            return SimpleNamespace(returncode=0, stdout=stdout, stderr="")
        if command[:2] == ("systemctl", "show"):
            return SimpleNamespace(
                returncode=0,
                stdout=f"{service_pid if state['started'] else 0}\n",
                stderr="",
            )
        if command[:3] == ("systemctl", "is-active", "--quiet"):
            return SimpleNamespace(
                returncode=0 if state["started"] else 3,
                stdout="",
                stderr="",
            )
        if command[:3] == ("systemctl", "enable", "--now"):
            state["started"] = True
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if command[:2] == ("systemctl", "enable"):
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if command[:2] == ("systemctl", "restart"):
            state["started"] = True
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        raise AssertionError(command)

    runtime = SimpleNamespace(
        DEFAULT_PORT=8447,
        SERVICE="sg-gateway-naiveproxy.service",
        _load=lambda: ({"port": 8447}, [], []),
        _run=run,
    )

    def sync():
        result = runtime._run(
            ["systemctl", "enable", "--now", runtime.SERVICE],
            timeout=60,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr or "NaiveProxy restart failed")
        return {"ok": True}

    runtime.sync = sync
    return runtime, calls


def test_apply_fails_when_systemd_returns_success_without_owned_listener(monkeypatch):
    runtime, _calls = _runtime(
        initially_active=False,
        listener_after_apply=False,
    )
    monkeypatch.setattr(listener_patch, "_READINESS_ATTEMPTS", 1, raising=False)
    monkeypatch.setattr(listener_patch, "_READINESS_DELAY", 0, raising=False)
    listener_patch.install(runtime)

    with pytest.raises(RuntimeError, match="listener"):
        runtime.sync()


def test_reapply_restarts_an_already_active_service(monkeypatch):
    runtime, calls = _runtime(
        initially_active=True,
        listener_after_apply=True,
    )
    monkeypatch.setattr(listener_patch, "_READINESS_ATTEMPTS", 1, raising=False)
    monkeypatch.setattr(listener_patch, "_READINESS_DELAY", 0, raising=False)
    listener_patch.install(runtime)

    assert runtime.sync() == {"ok": True}
    assert (
        "systemctl",
        "restart",
        "sg-gateway-naiveproxy.service",
    ) in calls
