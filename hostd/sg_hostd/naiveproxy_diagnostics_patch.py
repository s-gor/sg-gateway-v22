from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


def _read_state(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _read_env(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return result
    for line in lines:
        key, separator, value = line.partition("=")
        if separator and key.strip():
            result[key.strip()] = value.strip()
    return result


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _service_main_pid(runtime) -> int:
    try:
        result = runtime._run(
            [
                "systemctl",
                "show",
                runtime.SERVICE,
                "--property",
                "MainPID",
                "--value",
            ],
            timeout=10,
        )
    except (OSError, RuntimeError):
        return 0
    if result.returncode != 0:
        return 0
    try:
        pid = int((result.stdout or "").strip())
    except (TypeError, ValueError):
        return 0
    return pid if pid > 0 else 0


def _listener(runtime, port: int) -> dict:
    try:
        result = runtime._run(["ss", "-H", "-ltnp"], timeout=15)
    except (OSError, RuntimeError):
        return {
            "listening": False,
            "owned_by_caddy": False,
            "owned_by_service": False,
            "service_main_pid": 0,
            "listener_pids": [],
        }
    lines = [
        line
        for line in (result.stdout or "").splitlines()
        if re.search(rf":{int(port)}\b", line)
    ]
    listener_pids = sorted(
        {
            int(value)
            for line in lines
            for value in re.findall(r"\bpid=(\d+)\b", line)
            if int(value) > 0
        }
    )
    service_pid = _service_main_pid(runtime)
    return {
        "listening": bool(lines),
        "owned_by_caddy": any("caddy" in line.lower() for line in lines),
        "owned_by_service": bool(service_pid and service_pid in listener_pids),
        "service_main_pid": service_pid,
        "listener_pids": listener_pids,
    }


def install(runtime) -> None:
    if getattr(runtime, "_naiveproxy_diagnostics_installed", False):
        return

    original_status = runtime.status

    def status() -> dict:
        result = dict(original_status())
        state = _read_state(runtime.STATE_PATH)
        settings = state.get("settings")
        settings = settings if isinstance(settings, dict) else {}
        port = int(settings.get("port") or result.get("port") or runtime.DEFAULT_PORT)
        versions_path = runtime.BINARY.parent.parent / "VERSIONS.env"
        metadata = _read_env(versions_path)
        expected_sha = str(metadata.get("RUNTIME_SHA256") or "").lower()

        installed = runtime.BINARY.is_file()
        actual_sha = ""
        binary_version = ""
        if installed:
            try:
                actual_sha = _sha256(runtime.BINARY)
            except OSError:
                actual_sha = ""
            version_result = runtime._run([str(runtime.BINARY), "version"], timeout=15)
            if version_result.returncode == 0:
                binary_version = runtime._redact(
                    (version_result.stdout or version_result.stderr).strip()
                )

        config_valid = False
        if installed and runtime.CONFIG_PATH.is_file():
            validation = runtime._run(
                [
                    str(runtime.BINARY),
                    "validate",
                    "--config",
                    str(runtime.CONFIG_PATH),
                    "--adapter",
                    "caddyfile",
                ],
                timeout=30,
            )
            config_valid = validation.returncode == 0

        listener = _listener(runtime, port)
        checksum_ok = bool(
            installed
            and expected_sha
            and actual_sha
            and actual_sha == expected_sha
        )
        active = bool(result.get("active"))
        result.update(
            {
                "installed": installed,
                "runtime_version": binary_version,
                "runtime_release": str(metadata.get("RUNTIME_VERSION") or ""),
                "runtime_sha256": actual_sha,
                "expected_sha256": expected_sha,
                "checksum_ok": checksum_ok,
                "config_valid": config_valid,
                "listener": listener,
                "firewall": state.get("firewall") or {},
                "port": port,
            }
        )
        result["ok"] = bool(
            active
            and checksum_ok
            and config_valid
            and listener["listening"]
            and listener["owned_by_service"]
        )
        return result

    runtime.status = status
    runtime._naiveproxy_diagnostics_installed = True
