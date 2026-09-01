from __future__ import annotations

from functools import wraps


def install(runtime) -> None:
    if getattr(install, "_installed", False):
        return
    original = runtime.sync

    @wraps(original)
    def sync():
        settings, _, _ = runtime._load()
        port = int(settings.get("port") or runtime.DEFAULT_PORT)
        result = runtime._run(["ss", "-H", "-ltnp"], timeout=10)
        if result.returncode != 0:
            raise RuntimeError("Cannot inspect TCP listeners before NaiveProxy apply")
        needle = f":{port}"
        for line in result.stdout.splitlines():
            fields = line.split()
            if len(fields) < 4 or not any(field.endswith(needle) for field in fields[3:5]):
                continue
            if "caddy" not in line.lower():
                raise RuntimeError(f"TCP port {port} is already occupied")
        return original()

    runtime.sync = sync
    install._installed = True
