from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "hostd"))

from sg_hostd import naiveproxy_commands, naiveproxy_runtime


@dataclass(frozen=True)
class _Result:
    command: str
    status: str
    message: str
    payload: dict


def _commands(base_status: str = "ok"):
    base = _Result(
        command="clients.apply",
        status=base_status,
        message="base applied" if base_status == "ok" else "base failed",
        payload={"xray": {"ok": base_status == "ok"}},
    )
    return SimpleNamespace(
        HostCommandResult=_Result,
        _COMMANDS={"clients.apply": lambda: base},
    )


def test_common_clients_apply_skips_naiveproxy_when_unused(monkeypatch):
    commands = _commands()
    sync_calls: list[bool] = []
    monkeypatch.setattr(
        naiveproxy_runtime,
        "_load",
        lambda: ({"domain": "", "port": 8447}, [], []),
    )
    monkeypatch.setattr(
        naiveproxy_runtime,
        "sync",
        lambda: sync_calls.append(True) or {"ok": True},
    )

    naiveproxy_commands.install(commands)
    result = commands._COMMANDS["clients.apply"]()

    assert result.status == "ok"
    assert result.payload == {"xray": {"ok": True}}
    assert sync_calls == []


def test_base_runtime_failure_does_not_touch_naiveproxy(monkeypatch):
    commands = _commands(base_status="error")
    sync_calls: list[bool] = []
    monkeypatch.setattr(
        naiveproxy_runtime,
        "sync",
        lambda: sync_calls.append(True) or {"ok": True},
    )

    naiveproxy_commands.install(commands)
    result = commands._COMMANDS["clients.apply"]()

    assert result.status == "error"
    assert result.message == "base failed"
    assert sync_calls == []


def test_naiveproxy_failure_makes_whole_clients_apply_fail(monkeypatch):
    commands = _commands()
    monkeypatch.setattr(
        naiveproxy_runtime,
        "_load",
        lambda: (
            {"domain": "vpn.example.test", "port": 8447},
            [{"username": "sg-1", "password": "not-returned"}],
            [41],
        ),
    )
    monkeypatch.setattr(
        naiveproxy_runtime,
        "sync",
        lambda: (_ for _ in ()).throw(RuntimeError("Caddy validation failed")),
    )

    naiveproxy_commands.install(commands)
    result = commands._COMMANDS["clients.apply"]()

    assert result.status == "error"
    assert result.command == "clients.apply"
    assert "Caddy validation failed" in result.message
    assert result.payload["service"] == "sg-gateway-naiveproxy.service"
    assert "password" not in repr(result.payload).lower()


def test_successful_clients_apply_returns_safe_naiveproxy_counts(monkeypatch):
    commands = _commands()
    monkeypatch.setattr(
        naiveproxy_runtime,
        "_load",
        lambda: (
            {"domain": "vpn.example.test", "port": 9447},
            [
                {"username": "sg-1", "password": "secret-one"},
                {"username": "sg-2", "password": "secret-two"},
            ],
            [41, 42],
        ),
    )
    monkeypatch.setattr(
        naiveproxy_runtime,
        "sync",
        lambda: {
            "ok": True,
            "service": "sg-gateway-naiveproxy.service",
            "port": 9447,
            "users": 2,
        },
    )

    naiveproxy_commands.install(commands)
    result = commands._COMMANDS["clients.apply"]()
    rendered = repr(result.payload).lower()

    assert result.status == "ok"
    assert result.payload["xray"] == {"ok": True}
    assert result.payload["naiveproxy"] == {
        "service": "sg-gateway-naiveproxy.service",
        "port": 9447,
        "users": 2,
        "credentials": 2,
    }
    assert "secret-one" not in rendered
    assert "secret-two" not in rendered
    assert "password" not in rendered
