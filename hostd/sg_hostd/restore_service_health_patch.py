from __future__ import annotations

from types import ModuleType


def install(restore: ModuleType) -> None:
    original = restore._local_panel_health

    def health(full: ModuleType) -> None:
        original(full)
        hostd = full._probe(
            ["systemctl", "is-active", "--quiet", "sg-hostd.service"],
            timeout=15,
        )
        if hostd.returncode != 0:
            detail = (hostd.stderr or hostd.stdout or "").strip()[-800:]
            suffix = f": {detail}" if detail else ""
            raise RuntimeError("SG-Gateway hostd is not active after restore" + suffix)

    restore._local_panel_health = health
