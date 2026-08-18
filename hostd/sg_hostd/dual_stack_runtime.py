from __future__ import annotations

import os
from pathlib import Path

from app.net import detect_global_ipv6, global_ip


RUNTIME_ENV = Path("/etc/sg-gateway/runtime.env")
APP_ENV = Path("/etc/sg-gateway/sg-gateway.env")


def _read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return values
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"\'')
    return values


def _update_env(path: Path, values: dict[str, str]) -> None:
    if not path.is_file():
        return
    lines = path.read_text(encoding="utf-8").splitlines()
    wanted = dict(values)
    output: list[str] = []
    for line in lines:
        if "=" not in line or line.lstrip().startswith("#"):
            output.append(line)
            continue
        key = line.split("=", 1)[0].strip()
        if key in wanted:
            output.append(f"{key}={wanted.pop(key)}")
        else:
            output.append(line)
    output.extend(f"{key}={value}" for key, value in wanted.items())

    temporary = path.with_name(path.name + ".dual-stack.new")
    temporary.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def refresh_runtime_metadata() -> dict[str, object]:
    """Refresh optional dual-stack facts after network-online.

    IPv4 keeps the established installer-detected public address. IPv6 is
    discovered from the host routing table and is deliberately optional.
    A missing IPv6 address therefore never invalidates an IPv4 installation.
    """
    runtime = _read_env(RUNTIME_ENV)
    legacy_address = str(runtime.get("SG_GATEWAY_PUBLIC_ADDRESS") or "").strip()
    public_ipv4 = global_ip(legacy_address, 4)
    public_ipv6 = detect_global_ipv6()
    values = {
        "SG_GATEWAY_PUBLIC_IPV4": public_ipv4,
        "SG_GATEWAY_PUBLIC_IPV6": public_ipv6,
    }

    for path in (RUNTIME_ENV, APP_ENV):
        try:
            _update_env(path, values)
        except OSError:
            # Runtime refresh is an enhancement, never a hostd startup gate.
            continue

    return {
        "ipv4": public_ipv4,
        "ipv6": public_ipv6,
        "dual_stack": bool(public_ipv4 and public_ipv6),
    }
