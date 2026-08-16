from __future__ import annotations

import hashlib
import ipaddress
import json
import secrets as pysecrets
import shutil
import subprocess
from pathlib import Path

from sg_hostd import client_runtime as cr


ENGINE = "amneziawg3"
AWG3_PORT = 586
AWG3_CONFIG = Path("/etc/amnezia/amneziawg/awg3.conf")
AWG3_SERVICE = "sg-gateway-awg3.service"
AWG3_SUBNET = "10.67.0.0/16"
AWG3_IPV6_SUBNET_ID = 3
AWG3_ROOT = Path("/opt/sg-gateway/awg3")
AWG3_AWG = AWG3_ROOT / "bin/awg"
AWG3_AWG_QUICK = AWG3_ROOT / "bin/awg-quick"
AWG3_GO = AWG3_ROOT / "bin/amneziawg-go"
AWG3_HELPER = Path("/opt/sg-gateway/deploy/sg-gateway-awg3-userspace.sh")

AWG3_DEFAULTS = {
    "jc": 4,
    "jmin": 10,
    "jmax": 50,
    "s1": 64,
    "s2": 96,
    "s3": 48,
    "s4": 12,
    "content_padding_addition": "10-100",
    "rekey_after_time": "100-120",
    "rekey_timeout": "3-7",
    "reject_after_time": "150-180",
    "keepalive_timeout": "5-15",
    "max_handshake_attempts": "15-20",
    "persistent_keepalive": "25-35",
}


def _tool(path: Path) -> str:
    if not path.is_file():
        raise cr.ClientRuntimeError(f"AWG3 runtime tool missing: {path}")
    return str(path)


def _run_awg(args: list[str], *, input_text: str | None = None, timeout: int = 30):
    return cr._run([_tool(AWG3_AWG), *args], input_text=input_text, timeout=timeout)


def _address_values(value: str) -> list[str]:
    return [part.strip() for part in str(value or "").split(",") if part.strip()]


def _normalise_address(device_id: int, value: str) -> str:
    """Keep the frozen AWG3 IPv4 allocation contract."""
    for raw in _address_values(value):
        try:
            interface = ipaddress.ip_interface(raw)
            if interface.version == 4 and interface.ip in ipaddress.ip_network(AWG3_SUBNET):
                return str(interface)
        except ValueError:
            continue
    slot = max(1, int(device_id))
    third = min(254, slot // 250)
    fourth = 2 + (slot % 250)
    return f"10.67.{third}.{fourth}/32"


def _dual_stack_enabled() -> bool:
    runtime = cr._read_env(cr.RUNTIME_ENV)
    raw = str(runtime.get("SG_GATEWAY_PUBLIC_IPV6") or "").strip()
    try:
        address = ipaddress.ip_address(raw)
    except ValueError:
        return False
    return address.version == 6 and address.is_global


def _ipv6_network(server_public_key: str) -> ipaddress.IPv6Network:
    """Derive one stable RFC4193 /64 from this AWG3 server identity."""
    material = f"SG-Gateway:{ENGINE}:{server_public_key}".encode("utf-8")
    global_id = int.from_bytes(hashlib.sha256(material).digest()[:5], "big")
    network_value = (
        (0xFD << 120)
        | (global_id << 80)
        | (AWG3_IPV6_SUBNET_ID << 64)
    )
    return ipaddress.IPv6Network((network_value, 64))


def _normalise_ipv6_address(
    device_id: int,
    value: str,
    network: ipaddress.IPv6Network,
) -> str:
    for raw in _address_values(value):
        try:
            interface = ipaddress.ip_interface(raw)
            if interface.version == 6 and interface.ip in network:
                return f"{interface.ip}/128"
        except ValueError:
            continue
    slot = max(1, int(device_id))
    address = ipaddress.IPv6Address(int(network.network_address) + slot + 1)
    return f"{address}/128"


def _normalise_addresses(
    device_id: int,
    value: str,
    network: ipaddress.IPv6Network | None,
) -> str:
    ipv4 = _normalise_address(device_id, value)
    if network is None:
        return ipv4
    ipv6 = _normalise_ipv6_address(device_id, value, network)
    return f"{ipv4}, {ipv6}"


def _peer_allowed_ips(value: str) -> str:
    result: list[str] = []
    for raw in _address_values(value):
        try:
            interface = ipaddress.ip_interface(raw)
        except ValueError:
            continue
        suffix = 32 if interface.version == 4 else 128
        result.append(f"{interface.ip}/{suffix}")
    return ", ".join(result)


def _format_endpoint(host: str, port: int) -> str:
    value = str(host or "").strip()
    if not value:
        return ""
    if value.startswith("[") and value.endswith("]"):
        value = value[1:-1]
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        formatted = value
    else:
        formatted = f"[{address.compressed}]" if address.version == 6 else str(address)
    return f"{formatted}:{int(port)}"


def _derive_public(private_key: str) -> str:
    if not private_key:
        raise cr.ClientRuntimeError("AWG3: отсутствует приватный ключ")
    return _run_awg(["pubkey"], input_text=private_key.strip() + "\n").stdout.strip()


def _set_env_values(path: Path, values: dict[str, str]) -> None:
    existing: list[str] = []
    if path.is_file():
        existing = path.read_text(encoding="utf-8").splitlines()
    wanted = dict(values)
    output: list[str] = []
    for line in existing:
        if "=" not in line or line.lstrip().startswith("#"):
            output.append(line)
            continue
        key = line.split("=", 1)[0].strip()
        if key in wanted:
            output.append(f"{key}={wanted.pop(key)}")
        else:
            output.append(line)
    for key, value in wanted.items():
        output.append(f"{key}={value}")
    cr._atomic_write(path, "\n".join(output).rstrip() + "\n", 0o600)


def _independent_headers() -> list[str]:
    values: list[str] = []
    while len(values) < 4:
        value = str(100000 + pysecrets.randbelow(4_000_000_000))
        if value not in values:
            values.append(value)
    return values


def _sync_connection_public_key(public_key: str) -> None:
    settings = cr.get_connection_settings(ENGINE)
    config = dict(settings.config)
    config["server_public_key"] = public_key
    config["generation"] = 3
    runtime = cr._read_env(cr.RUNTIME_ENV)
    host = str(settings.host or runtime.get("SG_GATEWAY_PUBLIC_ADDRESS") or "").strip()
    if not host or not cr.update_connection_settings(ENGINE, host, AWG3_PORT, config):
        raise cr.ClientRuntimeError("AWG3: не удалось синхронизировать серверный public key")


def _ensure_server_secrets() -> dict[str, str]:
    secrets = cr._read_env(cr.ENGINE_SECRETS)
    required = (
        "SG_GATEWAY_AWG3_PRIVATE_KEY",
        "SG_GATEWAY_AWG3_PUBLIC_KEY",
        "SG_GATEWAY_AWG3_HEADER_PROTECTION_KEY",
    )
    if all(str(secrets.get(name) or "").strip() for name in required):
        _sync_connection_public_key(str(secrets["SG_GATEWAY_AWG3_PUBLIC_KEY"]).strip())
        return secrets

    private_key = _run_awg(["genkey"]).stdout.strip()
    public_key = _run_awg(["pubkey"], input_text=private_key + "\n").stdout.strip()
    header_key = _run_awg(["genkey"]).stdout.strip()
    if not private_key or not public_key or not header_key:
        raise cr.ClientRuntimeError("AWG3: не удалось создать серверные параметры")

    h1, h2, h3, h4 = _independent_headers()
    values = {
        "SG_GATEWAY_AWG3_PRIVATE_KEY": private_key,
        "SG_GATEWAY_AWG3_PUBLIC_KEY": public_key,
        "SG_GATEWAY_AWG3_HEADER_PROTECTION_KEY": header_key,
        "SG_GATEWAY_AWG3_JC": str(AWG3_DEFAULTS["jc"]),
        "SG_GATEWAY_AWG3_JMIN": str(AWG3_DEFAULTS["jmin"]),
        "SG_GATEWAY_AWG3_JMAX": str(AWG3_DEFAULTS["jmax"]),
        "SG_GATEWAY_AWG3_S1": str(AWG3_DEFAULTS["s1"]),
        "SG_GATEWAY_AWG3_S2": str(AWG3_DEFAULTS["s2"]),
        "SG_GATEWAY_AWG3_S3": str(AWG3_DEFAULTS["s3"]),
        "SG_GATEWAY_AWG3_S4": str(AWG3_DEFAULTS["s4"]),
        "SG_GATEWAY_AWG3_H1": h1,
        "SG_GATEWAY_AWG3_H2": h2,
        "SG_GATEWAY_AWG3_H3": h3,
        "SG_GATEWAY_AWG3_H4": h4,
        "SG_GATEWAY_AWG3_CONTENT_PADDING_ADDITION": str(AWG3_DEFAULTS["content_padding_addition"]),
        "SG_GATEWAY_AWG3_REKEY_AFTER_TIME": str(AWG3_DEFAULTS["rekey_after_time"]),
        "SG_GATEWAY_AWG3_REKEY_TIMEOUT": str(AWG3_DEFAULTS["rekey_timeout"]),
        "SG_GATEWAY_AWG3_REJECT_AFTER_TIME": str(AWG3_DEFAULTS["reject_after_time"]),
        "SG_GATEWAY_AWG3_KEEPALIVE_TIMEOUT": str(AWG3_DEFAULTS["keepalive_timeout"]),
        "SG_GATEWAY_AWG3_MAX_HANDSHAKE_ATTEMPTS": str(AWG3_DEFAULTS["max_handshake_attempts"]),
    }
    _set_env_values(cr.ENGINE_SECRETS, values)
    secrets = cr._read_env(cr.ENGINE_SECRETS)
    _sync_connection_public_key(public_key)
    return secrets


def _values(secrets: dict[str, str]) -> dict[str, object]:
    result: dict[str, object] = {}
    for name in ("jc", "jmin", "jmax", "s1", "s2", "s3", "s4"):
        env = f"SG_GATEWAY_AWG3_{name.upper()}"
        raw = str(secrets.get(env) or "").strip()
        try:
            result[name] = int(raw)
        except ValueError as exc:
            raise cr.ClientRuntimeError(f"AWG3: некорректный параметр {env}") from exc
    for name in ("h1", "h2", "h3", "h4"):
        env = f"SG_GATEWAY_AWG3_{name.upper()}"
        raw = str(secrets.get(env) or "").strip()
        if not raw:
            raise cr.ClientRuntimeError(f"AWG3: отсутствует параметр {env}")
        result[name] = raw

    if not 1 <= int(result["jc"]) <= 128:
        raise cr.ClientRuntimeError("AWG3: Jc вне допустимого диапазона")
    if not 1 <= int(result["jmin"]) <= int(result["jmax"]) <= 1280:
        raise cr.ClientRuntimeError("AWG3: Jmin/Jmax заданы некорректно")

    header_key = str(secrets.get("SG_GATEWAY_AWG3_HEADER_PROTECTION_KEY") or "").strip()
    if not header_key:
        raise cr.ClientRuntimeError("AWG3: HeaderProtectionKey отсутствует")
    if any(int(result[name]) < 12 for name in ("s1", "s2", "s3", "s4")):
        raise cr.ClientRuntimeError("AWG3: при HeaderProtectionKey S1-S4 должны быть не меньше 12")

    result.update({
        "header_protection_key": header_key,
        "content_padding_addition": str(secrets.get("SG_GATEWAY_AWG3_CONTENT_PADDING_ADDITION") or AWG3_DEFAULTS["content_padding_addition"]).strip(),
        "rekey_after_time": str(secrets.get("SG_GATEWAY_AWG3_REKEY_AFTER_TIME") or AWG3_DEFAULTS["rekey_after_time"]).strip(),
        "rekey_timeout": str(secrets.get("SG_GATEWAY_AWG3_REKEY_TIMEOUT") or AWG3_DEFAULTS["rekey_timeout"]).strip(),
        "reject_after_time": str(secrets.get("SG_GATEWAY_AWG3_REJECT_AFTER_TIME") or AWG3_DEFAULTS["reject_after_time"]).strip(),
        "keepalive_timeout": str(secrets.get("SG_GATEWAY_AWG3_KEEPALIVE_TIMEOUT") or AWG3_DEFAULTS["keepalive_timeout"]).strip(),
        "max_handshake_attempts": str(secrets.get("SG_GATEWAY_AWG3_MAX_HANDSHAKE_ATTEMPTS") or AWG3_DEFAULTS["max_handshake_attempts"]).strip(),
    })
    return result


def _repair_configs(secrets: dict[str, str]) -> None:
    settings = cr.get_connection_settings("amneziawg3")
    runtime = cr._read_env(cr.RUNTIME_ENV)
    public_address = str(runtime.get("SG_GATEWAY_PUBLIC_ADDRESS") or "").strip()
    server_public = str(secrets.get("SG_GATEWAY_AWG3_PUBLIC_KEY") or "").strip()
    ipv6_network = _ipv6_network(server_public) if _dual_stack_enabled() else None
    values = _values(secrets)
    with cr.connect() as connection:
        rows = connection.execute(
            """
            SELECT d.id AS device_id,
                   CASE WHEN d.is_primary = 1 THEN c.name ELSE c.name || ' · ' || d.name END AS client_name,
                   dc.config_json
            FROM devices d
            JOIN clients c ON c.id = d.client_id
            JOIN device_credentials dc ON dc.device_id = d.id AND dc.engine = 'amneziawg3'
            ORDER BY d.id
            """
        ).fetchall()
        for row in rows:
            device_id = int(row["device_id"])
            config = cr._json(row["config_json"])
            private_key = str(config.get("private_key") or "").strip()
            public_key = _derive_public(private_key)
            config.update({
                "client_name": str(row["client_name"]),
                "private_key": private_key,
                "public_key": public_key,
                "address": _normalise_addresses(device_id, str(config.get("address") or ""), ipv6_network),
                "dns": settings.config.get("dns", "1.1.1.1"),
                "server_public_key": server_public,
                "endpoint": _format_endpoint(str(settings.host or public_address), AWG3_PORT),
                "port": AWG3_PORT,
                "allowed_ips": settings.config.get("allowed_ips", "0.0.0.0/0, ::/0"),
                "persistent_keepalive": AWG3_DEFAULTS["persistent_keepalive"],
                "generation": 3,
                "dual_stack": ipv6_network is not None,
                "ipv6_network": str(ipv6_network) if ipv6_network is not None else "",
                **values,
            })
            connection.execute(
                """UPDATE device_credentials SET engine_object_id = ?, config_json = ?
                   WHERE device_id = ? AND engine = 'amneziawg3'""",
                (public_key, json.dumps(config, ensure_ascii=False, sort_keys=True), device_id),
            )


def _render(rows, secrets: dict[str, str]) -> str:
    server_private = str(secrets.get("SG_GATEWAY_AWG3_PRIVATE_KEY") or "").strip()
    server_public = str(secrets.get("SG_GATEWAY_AWG3_PUBLIC_KEY") or "").strip()
    if not server_private:
        raise cr.ClientRuntimeError("AWG3: серверный приватный ключ отсутствует")
    values = _values(secrets)
    external_interface = cr._default_interface()
    ipv6_network = _ipv6_network(server_public) if _dual_stack_enabled() else None
    server_address = "10.67.0.1/16"
    if ipv6_network is not None:
        server_ipv6 = ipaddress.IPv6Address(int(ipv6_network.network_address) + 1)
        server_address = f"{server_address}, {server_ipv6}/64"

    post_up = (
        "PostUp = nft delete table ip sg_gateway_awg3 2>/dev/null || true; "
        "nft add table ip sg_gateway_awg3; "
        "nft 'add chain ip sg_gateway_awg3 forward { type filter hook forward priority filter; policy accept; }'; "
        "nft 'add chain ip sg_gateway_awg3 postrouting { type nat hook postrouting priority srcnat; policy accept; }'; "
        f"nft add rule ip sg_gateway_awg3 postrouting oifname \"{external_interface}\" ip saddr 10.67.0.0/16 masquerade"
    )
    post_down = "PostDown = nft delete table ip sg_gateway_awg3 2>/dev/null || true"
    if ipv6_network is not None:
        post_up += (
            "; sysctl -w net.ipv6.conf.all.forwarding=1 >/dev/null; "
            "nft delete table ip6 sg_gateway_awg3 2>/dev/null || true; "
            "nft add table ip6 sg_gateway_awg3; "
            "nft 'add chain ip6 sg_gateway_awg3 forward { type filter hook forward priority filter; policy accept; }'; "
            "nft 'add chain ip6 sg_gateway_awg3 postrouting { type nat hook postrouting priority srcnat; policy accept; }'; "
            f"nft add rule ip6 sg_gateway_awg3 postrouting oifname \"{external_interface}\" ip6 saddr {ipv6_network} masquerade"
        )
        post_down += "; nft delete table ip6 sg_gateway_awg3 2>/dev/null || true"

    lines = [
        "[Interface]",
        f"Address = {server_address}",
        f"ListenPort = {AWG3_PORT}",
        f"PrivateKey = {server_private}",
        f"Jc = {values['jc']}", f"Jmin = {values['jmin']}", f"Jmax = {values['jmax']}",
        f"S1 = {values['s1']}", f"S2 = {values['s2']}", f"S3 = {values['s3']}", f"S4 = {values['s4']}",
        f"H1 = {values['h1']}", f"H2 = {values['h2']}", f"H3 = {values['h3']}", f"H4 = {values['h4']}",
        f"HeaderProtectionKey = {values['header_protection_key']}",
        f"ContentPaddingAddition = {values['content_padding_addition']}",
        f"RekeyAfterTime = {values['rekey_after_time']}",
        f"RekeyTimeout = {values['rekey_timeout']}",
        f"RejectAfterTime = {values['reject_after_time']}",
        f"KeepaliveTimeout = {values['keepalive_timeout']}",
        f"MaxHandshakeAttempts = {values['max_handshake_attempts']}",
        post_up,
        post_down,
        "",
    ]
    for row in rows:
        config = cr._json(row["config_json"])
        public_key = str(config.get("public_key") or "").strip()
        address = _normalise_addresses(
            int(row["client_id"]),
            str(config.get("address") or ""),
            ipv6_network,
        )
        if not public_key:
            raise cr.ClientRuntimeError(f"AWG3: отсутствует public key клиента {row['client_name']}")
        allowed_ips = _peer_allowed_ips(address)
        lines.extend(["[Peer]", f"# {row['client_name']} · device {row['client_id']}", f"PublicKey = {public_key}", f"AllowedIPs = {allowed_ips}", ""])
    return "\n".join(lines).rstrip() + "\n"


def _runtime_valid() -> bool:
    return bool(
        AWG3_CONFIG.is_file()
        and AWG3_AWG.is_file()
        and AWG3_AWG_QUICK.is_file()
        and AWG3_GO.is_file()
        and cr._command_ok([str(AWG3_AWG), "show", "awg3"], 30)
        and cr._command_ok(["systemctl", "is-active", "--quiet", AWG3_SERVICE], 30)
        and cr._udp_port_listening(AWG3_PORT)
    )


def apply_awg3() -> cr.EngineResult:
    _tool(AWG3_AWG)
    _tool(AWG3_AWG_QUICK)
    _tool(AWG3_GO)
    if not AWG3_HELPER.is_file():
        raise cr.ClientRuntimeError(f"AWG3 runtime helper missing: {AWG3_HELPER}")
    secrets = _ensure_server_secrets()
    _repair_configs(secrets)
    rows = cr._deployment_rows(ENGINE)
    ids = [int(row["client_id"]) for row in rows]
    previous = cr._status_snapshot(ENGINE)

    if not rows:
        subprocess.run(["systemctl", "stop", AWG3_SERVICE], capture_output=True, text=True, timeout=60, check=False)
        return cr.EngineResult(ENGINE, True, "Нет активных клиентов AWG3", 0)

    candidate = cr.CANDIDATE_DIR / "awg3.conf"
    backup = AWG3_CONFIG.with_suffix(".conf.previous")
    try:
        cr._set_engine_status(ENGINE, ids, "checking")
        body = _render(rows, secrets)
        cr._atomic_write(candidate, body, 0o600)
        cr._run([str(AWG3_AWG_QUICK), "strip", str(candidate)], timeout=30)

        cr._set_engine_status(ENGINE, ids, "applying")
        AWG3_CONFIG.parent.mkdir(parents=True, exist_ok=True)
        if AWG3_CONFIG.is_file():
            shutil.copy2(AWG3_CONFIG, backup)
        cr._atomic_write(AWG3_CONFIG, body, 0o600)
        cr._run(["systemctl", "daemon-reload"], timeout=30)
        cr._run(["systemctl", "enable", AWG3_SERVICE], timeout=30)
        cr._run(["systemctl", "restart", AWG3_SERVICE], timeout=90)
        cr._run(["systemctl", "is-active", "--quiet", AWG3_SERVICE], timeout=30)
        _run_awg(["show", "awg3"], timeout=30)
        if not cr._udp_port_listening(AWG3_PORT):
            raise cr.ClientRuntimeError("AWG3: runtime не слушает заданный endpoint после запуска")

        cr._set_engine_status(ENGINE, ids, "applied")
        return cr.EngineResult(ENGINE, True, f"AmneziaWG 3.0 userspace применён; клиентов: {len(rows)}", len(rows))
    except Exception as exc:
        if backup.is_file():
            shutil.copy2(backup, AWG3_CONFIG)
            subprocess.run(["systemctl", "restart", AWG3_SERVICE], capture_output=True, text=True, check=False)
        restored = _runtime_valid()
        cr._set_failure_status(ENGINE, ids, previous, runtime_restored=restored)
        return cr.EngineResult(ENGINE, False, f"AWG3 userspace: {exc}", len(rows))
