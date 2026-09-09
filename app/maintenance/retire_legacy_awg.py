from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable, Sequence


RETIRED_ENGINES = ("amneziawg", "amneziawg3")
LEGACY_UNITS = ("sg-gateway-awg.service", "sg-gateway-awg3.service")
LEGACY_INTERFACES = ("awg0", "awg3")
LEGACY_PATHS = (
    Path("/etc/systemd/system/sg-gateway-awg.service"),
    Path("/etc/systemd/system/sg-gateway-awg3.service"),
    Path("/etc/amnezia/amneziawg/awg0.conf"),
    Path("/etc/amnezia/amneziawg/awg3.conf"),
)

RunCommand = Callable[[Sequence[str]], int]


def _run(command: Sequence[str]) -> int:
    completed = subprocess.run(
        list(command),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return int(completed.returncode)


def retire_legacy_awg(*, run: RunCommand = _run) -> dict[str, object]:
    """Remove live AWG2/AWG3 runtime state without touching stored credentials.

    The legacy engines may still be present in old backups and in the database.
    Retirement is intentionally limited to live systemd/interface/config state;
    AWG3.1 (amneziawg31/awg31) and database rows are outside this function.
    """

    changed = False

    for unit in LEGACY_UNITS:
        run(("systemctl", "stop", unit))
        run(("systemctl", "disable", unit))

    for interface in LEGACY_INTERFACES:
        run(("ip", "link", "delete", "dev", interface))

    for path in LEGACY_PATHS:
        try:
            path.unlink()
            changed = True
        except FileNotFoundError:
            pass

    run(("systemctl", "daemon-reload"))
    run(("systemctl", "reset-failed"))

    return {
        "changed": changed,
        "message": "retired AWG2/AWG3 runtime state removed",
        "retired_engines": list(RETIRED_ENGINES),
    }
