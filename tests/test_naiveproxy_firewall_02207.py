from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest


MODULE_PATH = (
    Path(__file__).parents[1]
    / "hostd"
    / "sg_hostd"
    / "naiveproxy_firewall_patch.py"
)
SPEC = importlib.util.spec_from_file_location("naiveproxy_firewall_patch_test", MODULE_PATH)
patch = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(patch)


def _atomic_write(path: Path, content: str, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    path.chmod(mode)


def _runtime(tmp_path: Path, commands: list[list[str]], *, port: int = 8447, active: bool = True):
    state_path = tmp_path / "state.json"

    def run(command, timeout=30):
        commands.append(list(command))
        if command == ["ufw", "status"]:
            body = "Status: active\n" if active else "Status: inactive\n"
            return subprocess.CompletedProcess(command, 0, body, "")
        return subprocess.CompletedProcess(command, 0, "", "")

    def sync():
        _atomic_write(
            state_path,
            json.dumps({"settings": {"port": port}}) + "\n",
            0o600,
        )
        return {"ok": True, "port": port}

    return SimpleNamespace(
        STATE_PATH=state_path,
        _load=lambda: ({"port": port}, [], []),
        _run=run,
        _redact=lambda value: value,
        _atomic_write=_atomic_write,
        sync=sync,
        rollback=lambda restart=True: {"ok": True},
    )


def test_inactive_ufw_never_adds_a_hardcoded_port(tmp_path):
    commands: list[list[str]] = []
    runtime = _runtime(tmp_path, commands, port=9447, active=False)
    patch.install(runtime)

    result = runtime.sync()

    assert result["firewall"] == {
        "active": False,
        "managed": False,
        "port": None,
    }
    assert commands == [["ufw", "status"]]


def test_selected_custom_port_is_opened_before_runtime_apply(tmp_path):
    commands: list[list[str]] = []
    runtime = _runtime(tmp_path, commands, port=9447, active=True)
    patch.install(runtime)

    result = runtime.sync()

    assert commands[0] == ["ufw", "status"]
    assert commands[1] == [
        "ufw",
        "allow",
        "9447/tcp",
        "comment",
        "SG-Gateway NaiveProxy",
    ]
    assert result["firewall"] == {
        "active": True,
        "managed": True,
        "port": 9447,
    }


def test_new_rule_is_removed_when_runtime_apply_fails(tmp_path):
    commands: list[list[str]] = []
    runtime = _runtime(tmp_path, commands, port=9447, active=True)

    def failed_sync():
        raise RuntimeError("Caddy failed")

    runtime.sync = failed_sync
    patch.install(runtime)

    with pytest.raises(RuntimeError, match="Caddy failed"):
        runtime.sync()

    assert ["ufw", "--force", "delete", "allow", "9447/tcp"] in commands


def test_previous_managed_port_is_removed_only_after_new_apply(tmp_path):
    commands: list[list[str]] = []
    runtime = _runtime(tmp_path, commands, port=9447, active=True)
    runtime.STATE_PATH.write_text(
        json.dumps(
            {
                "settings": {"port": 8447},
                "firewall": {"active": True, "managed": True, "port": 8447},
            }
        ),
        encoding="utf-8",
    )
    patch.install(runtime)

    runtime.sync()

    allow_index = commands.index(
        ["ufw", "allow", "9447/tcp", "comment", "SG-Gateway NaiveProxy"]
    )
    delete_index = commands.index(
        ["ufw", "--force", "delete", "allow", "8447/tcp"]
    )
    assert allow_index < delete_index
    state = json.loads(runtime.STATE_PATH.read_text(encoding="utf-8"))
    assert state["firewall"] == {
        "active": True,
        "managed": True,
        "port": 9447,
    }
