from __future__ import annotations

import base64
import json
import os
import secrets
import subprocess
from pathlib import Path
from typing import Any

from app.clients.awg31_lifecycle import (
    DNS,
    ENDPOINT,
    ENGINE_ID,
    INTERFACE,
    NETWORK,
    PEER_CONFIG_DIR,
    RUNTIME_ROOT,
    SERVER_CONFIG,
    STATE_ROOT,
)
from app.connections.awg31 import (
    REAL31_DEFAULT_PARAMETERS,
    config_lines,
    get_settings,
    set_protocol_state,
    set_server_public_key,
)
from app.db import connect, init_db

SERVICE = "sg-gateway-awg31.service"
AWG = RUNTIME_ROOT / "bin/awg"


def _run(command: list[str], input_text: str | None = None) -> str:
    result = subprocess.run(
        command,
        input=input_text,
        capture_output=True,
        text=True,
        check=False,
        timeout=90,
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "AWG31 command failed").strip())
    return result.stdout.strip()


def _atomic_write(path: Path, body: str, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".new")
    temporary.write_text(body, encoding="utf-8", newline="\n")
    os.chmod(temporary, mode)
    os.replace(temporary, path)


def _server_keys() -> tuple[str, str]:
    STATE_ROOT.mkdir(parents=True, exist_ok=True)
    private_path = STATE_ROOT / "server-private.key"
    public_path = STATE_ROOT / "server-public.key"
    if private_path.is_file() and public_path.is_file():
        return private_path.read_text().strip(), public_path.read_text().strip()
    private_key = _run([str(AWG), "genkey"])
    public_key = _run([str(AWG), "pubkey"], private_key + "\n")
    _atomic_write(private_path, private_key + "\n")
    _atomic_write(public_path, public_key + "\n", 0o644)
    return private_key, public_key


def _independent_headers() -> list[str]:
    values: list[str] = []
    while len(values) < 4:
        value = str(100000 + secrets.randbelow(4_000_000_000))
        if value not in values:
            values.append(value)
    return values


def _header_protection_key() -> str:
    return base64.b64encode(secrets.token_bytes(32)).decode("ascii")


def _ensure_protocol_state():
    settings = get_settings()
    parameters = dict(settings.parameters)
    header_key = settings.header_protection_key
    changed = False

    if not header_key:
        header_key = _header_protection_key()
        h1, h2, h3, h4 = _independent_headers()
        parameters.update({"H1": h1, "H2": h2, "H3": h3, "H4": h4})
        changed = True
    elif [str(parameters.get(f"H{i}") or "") for i in range(1, 5)] == ["1", "2", "3", "4"]:
        h1, h2, h3, h4 = _independent_headers()
        parameters.update({"H1": h1, "H2": h2, "H3": h3, "H4": h4})
        changed = True

    for name, value in REAL31_DEFAULT_PARAMETERS.items():
        if name.startswith("I"):
            parameters.setdefault(name, value)
            continue
        current = parameters.get(name)
        if current is None or str(current).strip() == "":
            parameters[name] = value
            changed = True

    if any(int(parameters.get(f"S{i}") or 0) < 12 for i in range(1, 5)):
        for name in ("S1", "S2", "S3", "S4"):
            parameters[name] = REAL31_DEFAULT_PARAMETERS[name]
        changed = True

    if changed:
        return set_protocol_state(parameters, header_key)
    return settings


def _peers() -> list[dict[str, Any]]:
    init_db()
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT dc.device_id, dc.config_json
            FROM device_credentials dc
            JOIN devices d ON d.id = dc.device_id
            JOIN clients c ON c.id = d.client_id
            WHERE dc.engine = ? AND dc.status != 'disabled'
              AND d.enabled = 1 AND c.enabled = 1
            ORDER BY dc.device_id
            """,
            (ENGINE_ID,),
        ).fetchall()
    result: list[dict[str, Any]] = []
    for row in rows:
        payload = json.loads(row["config_json"] or "{}")
        if isinstance(payload, dict):
            payload["device_id"] = int(row["device_id"])
            result.append(payload)
    return result


def _peer_config(peer: dict[str, Any], server_public_key: str) -> str:
    settings = get_settings()
    return "\n".join(
        [
            "[Interface]",
            f"PrivateKey = {peer['private_key']}",
            f"Address = {peer['address']}",
            f"DNS = {DNS}",
            *config_lines(settings),
            "",
            "[Peer]",
            f"PublicKey = {server_public_key}",
            "AllowedIPs = 0.0.0.0/0",
            f"Endpoint = {ENDPOINT}",
            "PersistentKeepalive = 25",
            "",
        ]
    )


def render() -> dict[str, Any]:
    private_key, public_key = _server_keys()
    set_server_public_key(public_key)
    settings = _ensure_protocol_state()
    peers = _peers()
    peer_blocks: list[str] = []
    PEER_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    expected: set[Path] = set()
    for peer in peers:
        path = PEER_CONFIG_DIR / f"device-{peer['device_id']}.conf"
        expected.add(path)
        _atomic_write(path, _peer_config(peer, public_key))
        peer_blocks.extend(
            [
                "[Peer]",
                f"PublicKey = {peer['public_key']}",
                f"AllowedIPs = {peer['address']}",
                "",
            ]
        )
    for stale in PEER_CONFIG_DIR.glob("device-*.conf"):
        if stale not in expected:
            stale.unlink()
    body = "\n".join(
        [
            "[Interface]",
            f"PrivateKey = {private_key}",
            "ListenPort = 587",
            "Address = 10.131.0.1/24",
            *config_lines(settings),
            *peer_blocks,
        ]
    )
    _atomic_write(SERVER_CONFIG, body.rstrip() + "\n")
    return {
        "profile": "awg31",
        "interface": INTERFACE,
        "network": NETWORK,
        "endpoint": ENDPOINT,
        "transport": "udp",
        "config": str(SERVER_CONFIG),
        "peers": len(peers),
    }


def apply_awg31() -> dict[str, Any]:
    payload = render()
    _run(["systemctl", "daemon-reload"])
    _run(["systemctl", "enable", SERVICE])
    _run(["systemctl", "restart", SERVICE])
    _run(["systemctl", "is-active", "--quiet", SERVICE])
    with connect() as connection:
        connection.execute(
            "UPDATE device_credentials SET status = 'applied' WHERE engine = ?",
            (ENGINE_ID,),
        )
    return {"ok": True, **payload}


def activate_restored_awg31(*, enabled: bool, active: bool) -> dict[str, Any]:
    required = (
        SERVER_CONFIG,
        STATE_ROOT / "server-private.key",
        STATE_ROOT / "server-public.key",
        RUNTIME_ROOT / "bin/awg",
        RUNTIME_ROOT / "bin/awg-quick",
        RUNTIME_ROOT / "bin/amneziawg-go",
        Path("/etc/systemd/system") / SERVICE,
    )
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise RuntimeError("Restored AWG31 profile is incomplete: " + ", ".join(missing))
    with connect() as connection:
        peers = int(
            connection.execute(
                "SELECT COUNT(*) FROM device_credentials WHERE engine = ?",
                (ENGINE_ID,),
            ).fetchone()[0]
        )
    _run(["systemctl", "daemon-reload"])
    _run(["systemctl", "enable" if enabled else "disable", SERVICE])
    _run(["systemctl", "restart" if active else "stop", SERVICE])
    if active:
        _run(["systemctl", "is-active", "--quiet", SERVICE])
    return {
        "ok": True,
        "profile": "awg31",
        "peers": peers,
        "restored_exactly": True,
        "service_enabled": enabled,
        "service_active": active,
    }


def control(action: str) -> dict[str, Any]:
    if action not in {"start", "stop", "restart", "status"}:
        raise ValueError(action)
    if action == "status":
        result = subprocess.run(
            ["systemctl", "is-active", SERVICE], capture_output=True, text=True, check=False
        )
        return {"ok": result.returncode == 0, "status": result.stdout.strip() or "inactive"}
    _run(["systemctl", action, SERVICE])
    return {"ok": True, "action": action, "service": SERVICE}
