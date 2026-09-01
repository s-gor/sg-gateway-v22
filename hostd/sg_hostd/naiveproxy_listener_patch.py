from __future__ import annotations

import re
from functools import wraps


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
        needle = f":{port}"
        for line in (result.stdout or "").splitlines():
            fields = line.split()
            if len(fields) < 4 or not any(
                field.endswith(needle) for field in fields[3:5]
            ):
                continue
            listener_pids = _listener_pids(line)
            if service_pid <= 0 or service_pid not in listener_pids:
                raise RuntimeError(f"TCP port {port} is already occupied")
        return original()

    runtime.sync = sync
    runtime._naiveproxy_listener_guard_installed = True
