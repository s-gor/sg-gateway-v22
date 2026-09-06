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
    "naiveproxy_listener_patch_test", MODULE_PATH
)
listener_patch = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(listener_patch)


def _runtime(*, listener_pid: int | None, service_pid: int):
    calls: list[str] = []

    def run(command, timeout=10):
        if command[:3] == ["ss", "-H", "-ltnp"]:
            line = ""
            if listener_pid is not None:
                line = (
                    "LISTEN 0 4096 0.0.0.0:8447 0.0.0.0:* "
                    f'users:(("caddy",pid={listener_pid},fd=3))\n'
                )
            return SimpleNamespace(returncode=0, stdout=line, stderr="")
        if command[:2] == ["systemctl", "show"]:
            return SimpleNamespace(
                returncode=0,
                stdout=f"{service_pid}\n",
                stderr="",
            )
        raise AssertionError(command)

    def sync():
        calls.append("sync")
        return {"ok": True}

    return (
        SimpleNamespace(
            DEFAULT_PORT=8447,
            SERVICE="sg-gateway-naiveproxy.service",
            _load=lambda: ({"port": 8447}, [], []),
            _run=run,
            sync=sync,
        ),
        calls,
    )


def test_listener_guard_accepts_exact_service_main_pid():
    runtime, calls = _runtime(listener_pid=321, service_pid=321)
    listener_patch.install(runtime)

    assert runtime.sync() == {"ok": True}
    assert calls == ["sync"]


def test_listener_guard_rejects_unrelated_caddy_process():
    runtime, calls = _runtime(listener_pid=999, service_pid=321)
    listener_patch.install(runtime)

    with pytest.raises(RuntimeError, match="already occupied"):
        runtime.sync()

    assert calls == []


def test_listener_guard_allows_free_port_even_when_service_is_stopped():
    runtime, calls = _runtime(listener_pid=None, service_pid=0)
    listener_patch.install(runtime)

    assert runtime.sync() == {"ok": True}
    assert calls == ["sync"]
