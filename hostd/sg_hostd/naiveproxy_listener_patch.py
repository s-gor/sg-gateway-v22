from __future__ import annotations

import re
import subprocess
import time
from functools import wraps


_READINESS_ATTEMPTS = 20
_READINESS_DELAY = 0.25


def _service_main_pid(runtime) -> int:
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
    if result.returncode != 0:
        return 0
    try:
        pid = int((result.stdout or "").strip())
    except (TypeError, ValueError):
        return 0
    return pid if pid > 0 else 0


def _listener_pids(line: str) -> set[int]:
    return {
        int(value)
        for value in re.findall(r"\bpid=(\d+)\b", str(line))
        if int(value) > 0
    }


def _line_has_port(line: str, port: int) -> bool:
    fields = str(line).split()
    needle = f":{port}"
    return len(fields) >= 4 and any(
        field.endswith(needle) for field in fields[3:5]
    )


def _listener_owned_by_service(runtime, port: int) -> bool:
    active = runtime._run(
        ["systemctl", "is-active", "--quiet", runtime.SERVICE],
        timeout=10,
    )
    if active.returncode != 0:
        return False
    service_pid = _service_main_pid(runtime)
    if service_pid <= 0:
        return False
    result = runtime._run(["ss", "-H", "-ltnp"], timeout=10)
    if result.returncode != 0:
        return False
    for line in (result.stdout or "").splitlines():
        if not _line_has_port(line, port):
            continue
        if service_pid in _listener_pids(line):
            return True
    return False


def _listener_present(runtime, port: int) -> bool:
    result = runtime._run(["ss", "-H", "-ltnp"], timeout=10)
    if result.returncode != 0:
        return False
    return any(
        _line_has_port(line, port)
        for line in (result.stdout or "").splitlines()
    )


def _service_ready(runtime, port: int) -> bool:
    active = runtime._run(
        ["systemctl", "is-active", "--quiet", runtime.SERVICE],
        timeout=10,
    )
    return active.returncode == 0 and _listener_present(runtime, port)


def _wait_for_listener(runtime, port: int) -> bool:
    for attempt in range(_READINESS_ATTEMPTS):
        if _service_ready(runtime, port):
            return True
        if attempt + 1 < _READINESS_ATTEMPTS and _READINESS_DELAY > 0:
            time.sleep(_READINESS_DELAY)
    return False


def install(runtime) -> None:
    if getattr(runtime, "_naiveproxy_listener_guard_installed", False):
        return
    original = runtime.sync

    @wraps(original)
    def sync():
        settings, _, _ = runtime._load()
        port = int(settings.get("port") or runtime.DEFAULT_PORT)
        result = runtime._run(["ss", "-H", "-ltnp"], timeout=10)
        if result.returncode != 0:
            raise RuntimeError("Cannot inspect TCP listeners before NaiveProxy apply")
        service_pid = _service_main_pid(runtime)
        for line in (result.stdout or "").splitlines():
            if not _line_has_port(line, port):
                continue
            listener_pids = _listener_pids(line)
            if service_pid <= 0 or service_pid not in listener_pids:
                raise RuntimeError(f"TCP port {port} is already occupied")

        original_run = runtime._run

        def guarded_run(command, timeout=10):
            activation = ["systemctl", "enable", "--now", runtime.SERVICE]
            if list(command) != activation:
                return original_run(command, timeout=timeout)

            active = original_run(
                ["systemctl", "is-active", "--quiet", runtime.SERVICE],
                timeout=10,
            ).returncode == 0
            if active:
                enabled = original_run(
                    ["systemctl", "enable", runtime.SERVICE],
                    timeout=timeout,
                )
                if enabled.returncode != 0:
                    return enabled
                started = original_run(
                    ["systemctl", "restart", runtime.SERVICE],
                    timeout=timeout,
                )
            else:
                started = original_run(command, timeout=timeout)
            if started.returncode != 0:
                return started
            if _wait_for_listener(runtime, port):
                return started
            return subprocess.CompletedProcess(
                list(command),
                1,
                stdout=started.stdout,
                stderr=(
                    f"NaiveProxy listener {port} is not ready after "
                    f"{runtime.SERVICE} activation"
                ),
            )

        runtime._run = guarded_run
        try:
            return original()
        finally:
            runtime._run = original_run

    runtime.sync = sync
    runtime._naiveproxy_listener_guard_installed = True
