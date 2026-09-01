from __future__ import annotations

import json
import re
from pathlib import Path


COMMENT = "SG-Gateway NaiveProxy"


def _state(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _ufw_status(runtime) -> tuple[bool, str]:
    try:
        result = runtime._run(["ufw", "status"], timeout=15)
    except (OSError, RuntimeError):
        return False, ""
    text = (result.stdout or "") + "\n" + (result.stderr or "")
    active = result.returncode == 0 and bool(
        re.search(r"^Status:\s+active\s*$", text, re.MULTILINE | re.IGNORECASE)
    )
    return active, text


def _port_allowed(status_text: str, port: int) -> bool:
    return bool(
        re.search(
            rf"^\s*{int(port)}(?:/tcp)?\s+ALLOW\b",
            status_text,
            re.MULTILINE | re.IGNORECASE,
        )
    )


def _allow(runtime, port: int) -> None:
    result = runtime._run(
        ["ufw", "allow", f"{int(port)}/tcp", "comment", COMMENT],
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(
            runtime._redact(
                result.stderr
                or result.stdout
                or f"Cannot open NaiveProxy TCP port {port} in UFW"
            )
        )


def _delete(runtime, port: int) -> bool:
    result = runtime._run(
        ["ufw", "--force", "delete", "allow", f"{int(port)}/tcp"],
        timeout=30,
    )
    return result.returncode == 0


def _write_firewall_state(runtime, result: dict, firewall: dict) -> None:
    state = _state(runtime.STATE_PATH)
    state["firewall"] = firewall
    runtime._atomic_write(
        runtime.STATE_PATH,
        json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        0o600,
    )
    result["firewall"] = firewall


def install(runtime) -> None:
    if getattr(runtime, "_naiveproxy_firewall_installed", False):
        return

    original_sync = runtime.sync
    original_rollback = runtime.rollback

    def sync() -> dict:
        settings, _users, _credential_ids = runtime._load()
        target_port = int(settings["port"])
        previous_state = _state(runtime.STATE_PATH)
        previous_firewall = previous_state.get("firewall")
        previous_firewall = (
            previous_firewall if isinstance(previous_firewall, dict) else {}
        )
        previous_managed = bool(previous_firewall.get("managed"))
        previous_port = int(previous_firewall.get("port") or 0)

        active, status_text = _ufw_status(runtime)
        if not active:
            result = original_sync()
            _write_firewall_state(
                runtime,
                result,
                {"active": False, "managed": False, "port": None},
            )
            return result

        already_allowed = _port_allowed(status_text, target_port)
        added = False
        if not already_allowed:
            _allow(runtime, target_port)
            added = True

        try:
            result = original_sync()
        except Exception:
            if added:
                _delete(runtime, target_port)
            raise

        stale_ports: list[int] = []
        if previous_managed and previous_port and previous_port != target_port:
            if not _delete(runtime, previous_port):
                stale_ports.append(previous_port)

        managed = bool(added or (previous_managed and previous_port == target_port))
        firewall = {
            "active": True,
            "managed": managed,
            "port": target_port if managed else None,
        }
        if stale_ports:
            firewall["stale_ports"] = stale_ports
        _write_firewall_state(runtime, result, firewall)
        return result

    def rollback(restart: bool = True) -> dict:
        current_state = _state(runtime.STATE_PATH)
        current_firewall = current_state.get("firewall")
        current_firewall = (
            current_firewall if isinstance(current_firewall, dict) else {}
        )
        result = original_rollback(restart=restart)
        restored_state = _state(runtime.STATE_PATH)
        restored_firewall = restored_state.get("firewall")
        restored_firewall = (
            restored_firewall if isinstance(restored_firewall, dict) else {}
        )
        active, status_text = _ufw_status(runtime)
        if not active:
            return result

        desired_port = int(restored_firewall.get("port") or 0)
        desired_managed = bool(restored_firewall.get("managed"))
        current_port = int(current_firewall.get("port") or 0)
        current_managed = bool(current_firewall.get("managed"))
        if desired_managed and desired_port and not _port_allowed(status_text, desired_port):
            _allow(runtime, desired_port)
        if current_managed and current_port and current_port != desired_port:
            _delete(runtime, current_port)
        return result

    runtime.sync = sync
    runtime.rollback = rollback
    runtime._naiveproxy_firewall_installed = True
