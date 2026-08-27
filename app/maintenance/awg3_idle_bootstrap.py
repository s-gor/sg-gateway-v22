from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from app.db import connect
from sg_hostd import client_runtime as cr
from sg_hostd.awg3_runtime import (
    AWG3_AWG,
    AWG3_CONFIG,
    AWG3_PORT,
    AWG3_SERVICE,
    apply_awg3,
)


ENGINE = "amneziawg3"
INTERFACE = "awg3"
SOCKET = Path("/run/amneziawg/awg3.sock")


@dataclass(frozen=True)
class FileSnapshot:
    path: Path
    existed: bool
    content: bytes
    mode: int


def _snapshot_file(path: Path) -> FileSnapshot:
    try:
        stat = path.stat()
        return FileSnapshot(path, True, path.read_bytes(), stat.st_mode & 0o777)
    except FileNotFoundError:
        return FileSnapshot(path, False, b"", 0o600)


def _restore_file(snapshot: FileSnapshot) -> None:
    if not snapshot.existed:
        snapshot.path.unlink(missing_ok=True)
        return
    snapshot.path.parent.mkdir(parents=True, exist_ok=True)
    temporary = snapshot.path.with_name(snapshot.path.name + ".awg3-bootstrap-rollback")
    temporary.write_bytes(snapshot.content)
    os.chmod(temporary, snapshot.mode)
    os.replace(temporary, snapshot.path)


def _service_state() -> tuple[bool, bool]:
    active = subprocess.run(
        ["systemctl", "is-active", "--quiet", AWG3_SERVICE],
        check=False,
    ).returncode == 0
    enabled = subprocess.run(
        ["systemctl", "is-enabled", "--quiet", AWG3_SERVICE],
        check=False,
    ).returncode == 0
    return active, enabled


def _restore_service(active: bool, enabled: bool) -> None:
    subprocess.run(["systemctl", "daemon-reload"], check=False)
    subprocess.run(
        ["systemctl", "enable" if enabled else "disable", AWG3_SERVICE],
        check=False,
    )
    subprocess.run(
        ["systemctl", "restart" if active else "stop", AWG3_SERVICE],
        check=False,
    )


def _credential_count() -> int:
    with connect() as connection:
        row = connection.execute(
            "SELECT COUNT(*) FROM device_credentials WHERE engine = ?",
            (ENGINE,),
        ).fetchone()
    return int(row[0])


def _settings_snapshot() -> dict | None:
    with connect() as connection:
        row = connection.execute(
            """
            SELECT enabled, host, port, config_json, updated_at
            FROM connection_settings
            WHERE engine = ?
            """,
            (ENGINE,),
        ).fetchone()
    return dict(row) if row is not None else None


def _restore_settings(snapshot: dict | None) -> None:
    if snapshot is None:
        return
    with connect() as connection:
        connection.execute(
            """
            UPDATE connection_settings
            SET enabled = ?, host = ?, port = ?, config_json = ?, updated_at = ?
            WHERE engine = ?
            """,
            (
                snapshot["enabled"],
                snapshot["host"],
                snapshot["port"],
                snapshot["config_json"],
                snapshot["updated_at"],
                ENGINE,
            ),
        )


def _ready() -> bool:
    if not AWG3_CONFIG.is_file() or not SOCKET.is_socket():
        return False
    if subprocess.run(
        ["systemctl", "is-active", "--quiet", AWG3_SERVICE], check=False
    ).returncode != 0:
        return False
    if subprocess.run(
        ["ip", "link", "show", "dev", INTERFACE],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    ).returncode != 0:
        return False
    result = subprocess.run(
        [str(AWG3_AWG), "show", INTERFACE, "listen-port"],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0 and result.stdout.strip() == str(AWG3_PORT)


def bootstrap_idle_awg3() -> dict[str, object]:
    # Existing installations with real AWG3 peers are deliberately untouched.
    # Their apply path remains owned by the normal Clients transaction.
    if _credential_count() != 0:
        return {"changed": False, "message": "AWG3 idle bootstrap skipped: clients exist"}
    if _ready():
        return {"changed": False, "message": "AWG3 idle runtime already initialized"}

    required = (
        AWG3_AWG,
        Path("/opt/sg-gateway/awg3/bin/awg-quick"),
        Path("/opt/sg-gateway/awg3/bin/amneziawg-go"),
        Path("/opt/sg-gateway/deploy/sg-gateway-awg3-userspace.sh"),
    )
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        return {
            "changed": False,
            "message": "AWG3 idle bootstrap skipped: runtime is not installed",
            "missing": missing,
        }

    file_snapshots = (
        _snapshot_file(AWG3_CONFIG),
        _snapshot_file(cr.ENGINE_SECRETS),
    )
    settings = _settings_snapshot()
    active, enabled = _service_state()

    try:
        result = apply_awg3()
        if not result.ok:
            raise RuntimeError(result.message)
        if not _ready():
            raise RuntimeError("AWG3 bootstrap completed without a ready UDP 586 runtime")
        return {"changed": True, "message": result.message}
    except Exception:
        for snapshot in file_snapshots:
            _restore_file(snapshot)
        _restore_settings(settings)
        _restore_service(active, enabled)
        raise


def main() -> int:
    result = bootstrap_idle_awg3()
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
