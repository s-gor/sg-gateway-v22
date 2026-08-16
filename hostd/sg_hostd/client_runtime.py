from __future__ import annotations

import copy
import fcntl
import hashlib
import ipaddress
import json
import os
import pwd
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.connections.settings import get_connection_settings, update_connection_settings
from app.db import connect, init_db
from app.maintenance.operations import log_operation
from app.net import format_host_port
from app.security.tls import overview as tls_overview
from app.xray.encryption import VlessEncryptionError, normalize_pair
from app.xray.profiles import REALITY_TCP_FLOW, XRAY_MINIMUM_VERSION, overview as xray_profiles_overview
from app.xray.salamander import SalamanderError, merge_finalmask
from app.xray.settings_transactions import commit as commit_settings_transaction, pending as pending_settings_transaction, rollback as rollback_settings_transaction, update_candidate_config as update_settings_candidate_config
from app.xray.sg_panel_vless import reality_tcp_inbound, xhttp_reality_inbound


class ClientRuntimeError(RuntimeError):
    pass


@dataclass(frozen=True)
class EngineResult:
    engine: str
    ok: bool
    message: str
    clients: int


PREFIX = Path("/opt/sg-gateway")
CONFIG_DIR = Path("/etc/sg-gateway")
DATA_DIR = Path("/var/lib/sg-gateway")
CANDIDATE_DIR = DATA_DIR / "runtime-candidates"

XRAY_CONFIG = Path("/usr/local/etc/xray/config.json")
XRAY_TLS_DIR = Path("/usr/local/etc/xray/tls")
XRAY_TLS_CERT = XRAY_TLS_DIR / "fullchain.pem"
XRAY_TLS_KEY = XRAY_TLS_DIR / "privkey.pem"
LETSENCRYPT_LIVE_ROOT = Path("/etc/letsencrypt/live")
AWG_CONFIG = Path("/etc/amnezia/amneziawg/awg0.conf")
AWG_SERVICE = "sg-gateway-awg.service"
AWG_IPV6_SUBNET_ID = 2

ENGINE_SECRETS = CONFIG_DIR / "engine-secrets.env"
RUNTIME_ENV = CONFIG_DIR / "runtime.env"
LOCK_FILE = Path("/run/sg-gateway/clients-apply.lock")
SINGBOX_CONFIG = Path("/etc/sing-box/config.json")
SINGBOX_SERVICE = "sg-gateway-singbox.service"
ROUTING_MANAGED = Path("/etc/sg-gateway/xray-routing-managed.json")


def _load_managed_routing() -> dict:
    # Xray already uses the first outbound when no rule matches.  Keep the
    # safe fallback implicit so a panel update does not alter a previously
    # working runtime just to express "everything else -> Direct".
    default = {"domainStrategy": "AsIs", "rules": []}
    try:
        payload = json.loads(ROUTING_MANAGED.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return default
    routing = payload.get("routing") if isinstance(payload, dict) else None
    if not isinstance(routing, dict) or not isinstance(routing.get("rules"), list):
        raise ClientRuntimeError("Managed Routing повреждён")
    rules: list[dict] = []
    for index, raw in enumerate(routing["rules"], start=1):
        if not isinstance(raw, dict):
            raise ClientRuntimeError(f"Managed Routing rule {index} повреждён")
        tag = str(raw.get("outboundTag") or "")
        if tag not in {"direct", "warp", "block"}:
            # Preview 40 stored a decorative xray/proxy outbound. Ignore the
            # entire legacy fragment instead of breaking client application.
            return default
        if tag == "warp":
            try:
                from app.routing.warp import enabled as warp_enabled
            except ImportError as exc:
                raise ClientRuntimeError("Модуль WARP недоступен") from exc
            if not warp_enabled():
                raise ClientRuntimeError(
                    "Managed Routing использует WARP, но WARP выключен"
                )
        item = dict(raw)
        item["type"] = "field"
        item["outboundTag"] = tag
        rules.append(item)
    return {
        "domainStrategy": str(routing.get("domainStrategy") or ("IPIfNonMatch" if rules else "AsIs")),
        "rules": rules,
    }


def _read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ClientRuntimeError(f"Не найден обязательный файл {path}: {exc}") from exc

    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        value = value.strip()
        if (
            len(value) >= 2
            and value[0] == value[-1]
            and value[0] in {'"', "'"}
        ):
            value = value[1:-1]
        values[name.strip()] = value
    return values


def _run(
    command: list[str],
    *,
    input_text: str | None = None,
    timeout: int = 120,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        input=input_text,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise ClientRuntimeError(
            detail or f"Команда завершилась с кодом {result.returncode}: {' '.join(command)}"
        )
    return result


def _installed_xray_version() -> str:
    result = _run(["/usr/local/bin/xray", "version"], timeout=15)
    first = (result.stdout or result.stderr or "").splitlines()
    if not first:
        raise ClientRuntimeError("Xray не вернул версию")
    parts = first[0].split()
    if len(parts) < 2:
        raise ClientRuntimeError(f"Не удалось разобрать версию Xray: {first[0]}")
    return parts[1].lstrip("v")


def _version_key(value: str) -> tuple[int, ...]:
    try:
        return tuple(int(part) for part in str(value or "").lstrip("v").split("."))
    except (TypeError, ValueError):
        return ()


def _require_xray_version() -> str:
    installed = _installed_xray_version()
    current = _version_key(installed)
    minimum = _version_key(XRAY_MINIMUM_VERSION)
    width = max(len(current), len(minimum)) if current and minimum else 0
    supported = bool(
        width
        and current + (0,) * (width - len(current))
        >= minimum + (0,) * (width - len(minimum))
    )
    if not supported:
        raise ClientRuntimeError(
            f"Требуется Xray {XRAY_MINIMUM_VERSION} или новее, "
            f"установлен {installed or 'неизвестно'}"
        )
    return installed


def _xray_service_group_gid() -> int:
    result = subprocess.run(
        ["systemctl", "show", "-p", "User", "--value", "xray.service"],
        capture_output=True,
        text=True,
        check=False,
    )
    service_user = result.stdout.strip() or "root"
    if service_user == "root":
        return 0
    try:
        return pwd.getpwnam(service_user).pw_gid
    except KeyError as exc:
        raise ClientRuntimeError(
            f"Не найден пользователь xray.service: {service_user}"
        ) from exc


def _atomic_write(path: Path, body: str, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".new")
    temporary.write_text(body, encoding="utf-8", newline="\n")
    # SG_GATEWAY_02111_XRAY_FULL_ACCESS_POLICY
    if path == XRAY_CONFIG:
        os.chown(temporary, 0, _xray_service_group_gid())
        os.chmod(temporary, 0o777)
        try:
            os.chmod(path.parent, 0o777)
        except OSError:
            pass
    else:
        os.chown(temporary, 0, 0)
        os.chmod(temporary, mode)
    os.replace(temporary, path)


def _json(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        payload = json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _deployment_rows(engine: str, active_only: bool = True):
    where = """
        dc.engine = ?
        AND dc.status != 'disabled'
    """
    if active_only:
        where += " AND c.enabled = 1 AND d.enabled = 1"

    with connect() as connection:
        return connection.execute(
            f"""
            SELECT
                d.id AS client_id,
                c.id AS owner_client_id,
                CASE WHEN d.is_primary = 1 THEN c.name
                     ELSE c.name || ' · ' || d.name END AS client_name,
                c.enabled AS client_enabled,
                d.enabled AS device_enabled,
                dc.status,
                dc.engine_object_id,
                dc.config_json
            FROM devices d
            JOIN clients c ON c.id = d.client_id
            JOIN device_credentials dc ON dc.device_id = d.id
            WHERE {where}
            ORDER BY d.id
            """,
            (engine,),
        ).fetchall()


def _status_snapshot(engine: str) -> dict[int, str]:
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT device_id AS client_id, status
            FROM device_credentials
            WHERE engine = ?
            """,
            (engine,),
        ).fetchall()
    return {int(row["client_id"]): str(row["status"]) for row in rows}


def _set_engine_status(
    engine: str,
    client_ids: list[int],
    status: str,
) -> None:
    if not client_ids:
        return
    placeholders = ",".join("?" for _ in client_ids)
    with connect() as connection:
        connection.execute(
            f"""
            UPDATE device_credentials
            SET status = ?
            WHERE engine = ?
              AND device_id IN ({placeholders})
            """,
            (status, engine, *client_ids),
        )


def _set_failure_status(
    engine: str,
    client_ids: list[int],
    previous: dict[int, str],
    *,
    runtime_restored: bool = False,
) -> None:
    with connect() as connection:
        for client_id in client_ids:
            old = previous.get(client_id, "pending")
            status = (
                "applied"
                if old == "applied" and runtime_restored
                else "error"
            )
            connection.execute(
                """
                UPDATE device_credentials
                SET status = ?
                WHERE engine = ? AND device_id = ?
                """,
                (status, engine, client_id),
            )


def _command_ok(command: list[str], timeout: int = 60) -> bool:
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def _udp_port_listening(port: int) -> bool:
    try:
        result = subprocess.run(
            ["ss", "-H", "-lun"],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    if result.returncode != 0:
        return False
    pattern = re.compile(rf"(?:\]|:){int(port)}\b")
    return any(pattern.search(line) for line in result.stdout.splitlines())


def _salamander_change_message(transaction) -> str:
    if transaction is None:
        return ""
    previous = transaction.previous_config
    candidate = transaction.candidate_config
    old_mode = str(previous.get("hysteria2_obfs_mode") or "none")
    new_mode = str(candidate.get("hysteria2_obfs_mode") or "none")
    old_password = str(previous.get("hysteria2_obfs_password") or "")
    new_password = str(candidate.get("hysteria2_obfs_password") or "")
    if old_mode == "salamander" and new_mode == "salamander" and old_password != new_password:
        return "Hysteria2 Salamander password rotated; Server: local; Inbound: sg-hysteria2; Actor: admin"
    if old_mode != new_mode:
        return f"Hysteria2 Salamander mode changed: {old_mode} -> {new_mode}; Inbound: sg-hysteria2; Actor: admin"
    return ""


def _awg_runtime_valid() -> bool:
    return bool(
        AWG_CONFIG.is_file()
        and _command_ok(["awg-quick", "strip", str(AWG_CONFIG)], 30)
        and _command_ok(["systemctl", "is-active", "--quiet", AWG_SERVICE], 30)
    )


def _xray_runtime_valid() -> bool:
    return bool(
        XRAY_CONFIG.is_file()
        and _command_ok(
            [
                "/usr/local/bin/xray",
                "run",
                "-test",
                "-config",
                str(XRAY_CONFIG),
            ],
            60,
        )
        and _command_ok(
            ["systemctl", "is-active", "--quiet", "xray.service"],
            30,
        )
    )


def _mihomo_runtime_valid() -> bool:
    config = Path("/etc/mihomo/config.yaml")
    state_dir = Path("/var/lib/mihomo")
    return bool(
        config.is_file()
        and _command_ok(
            [
                "/usr/local/bin/mihomo",
                "-t",
                "-d",
                str(state_dir),
                "-f",
                str(config),
            ],
            60,
        )
        and _command_ok(
            ["systemctl", "is-active", "--quiet", "mihomo.service"],
            30,
        )
    )


def _awg_obfuscation(secrets: dict[str, str]) -> dict[str, int]:
    names = {
        "jc": "SG_GATEWAY_AWG_JC",
        "jmin": "SG_GATEWAY_AWG_JMIN",
        "jmax": "SG_GATEWAY_AWG_JMAX",
        "s1": "SG_GATEWAY_AWG_S1",
        "s2": "SG_GATEWAY_AWG_S2",
        "h1": "SG_GATEWAY_AWG_H1",
        "h2": "SG_GATEWAY_AWG_H2",
        "h3": "SG_GATEWAY_AWG_H3",
        "h4": "SG_GATEWAY_AWG_H4",
    }
    values: dict[str, int] = {}
    for key, env_name in names.items():
        raw = str(secrets.get(env_name) or "").strip()
        try:
            values[key] = int(raw)
        except ValueError as exc:
            raise ClientRuntimeError(
                f"Некорректный параметр AmneziaWG {env_name}"
            ) from exc

    if not 1 <= values["jc"] <= 128:
        raise ClientRuntimeError("AmneziaWG Jc вне допустимого диапазона")
    if not 1 <= values["jmin"] <= values["jmax"] <= 1280:
        raise ClientRuntimeError("AmneziaWG Jmin/Jmax заданы некорректно")
    if not 0 <= values["s1"] <= 2000 or not 0 <= values["s2"] <= 2000:
        raise ClientRuntimeError("AmneziaWG S1/S2 заданы некорректно")
    headers = [values[f"h{index}"] for index in range(1, 5)]
    if any(value <= 0 for value in headers) or len(set(headers)) != 4:
        raise ClientRuntimeError("AmneziaWG H1-H4 должны быть положительными и уникальными")
    return values


def _derive_awg_public(private_key: str) -> str:
    if not private_key:
        raise ClientRuntimeError("У клиента отсутствует приватный ключ AmneziaWG")
    return _run(
        ["awg", "pubkey"],
        input_text=private_key.strip() + "\n",
        timeout=30,
    ).stdout.strip()


def _address_values(value: str) -> list[str]:
    return [part.strip() for part in str(value or "").split(",") if part.strip()]


def _normalise_awg_address(client_id: int, value: str) -> str:
    for raw in _address_values(value):
        try:
            interface = ipaddress.ip_interface(raw)
            if interface.version == 4:
                return str(interface)
        except ValueError:
            continue

    # Deterministic address inside 10.66.0.0/16.
    slot = max(1, int(client_id))
    third = min(254, slot // 250)
    fourth = 2 + (slot % 250)
    return f"10.66.{third}.{fourth}/32"


def _dual_stack_enabled(runtime: dict[str, str] | None = None) -> bool:
    values = runtime if runtime is not None else _read_env(RUNTIME_ENV)
    raw = str(values.get("SG_GATEWAY_PUBLIC_IPV6") or "").strip()
    try:
        address = ipaddress.ip_address(raw)
    except ValueError:
        return False
    return address.version == 6 and address.is_global


def _awg_ipv6_network(server_public_key: str) -> ipaddress.IPv6Network:
    material = f"SG-Gateway:amneziawg:{server_public_key}".encode("utf-8")
    global_id = int.from_bytes(hashlib.sha256(material).digest()[:5], "big")
    network_value = (
        (0xFD << 120)
        | (global_id << 80)
        | (AWG_IPV6_SUBNET_ID << 64)
    )
    return ipaddress.IPv6Network((network_value, 64))


def _normalise_awg_ipv6_address(
    client_id: int,
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
    slot = max(1, int(client_id))
    address = ipaddress.IPv6Address(int(network.network_address) + slot + 1)
    return f"{address}/128"


def _normalise_awg_addresses(
    client_id: int,
    value: str,
    network: ipaddress.IPv6Network | None,
) -> str:
    ipv4 = _normalise_awg_address(client_id, value)
    if network is None:
        return ipv4
    ipv6 = _normalise_awg_ipv6_address(client_id, value, network)
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


def _repair_deployment_configs() -> None:
    secrets = _read_env(ENGINE_SECRETS)
    runtime = _read_env(RUNTIME_ENV)

    public_address = runtime.get("SG_GATEWAY_PUBLIC_ADDRESS", "").strip()
    awg_server_public = secrets.get("SG_GATEWAY_AWG_PUBLIC_KEY", "").strip()
    xray_public = secrets.get("SG_GATEWAY_XRAY_PUBLIC_KEY", "").strip()
    xray_short_id = secrets.get("SG_GATEWAY_XRAY_SHORT_ID", "").strip()
    awg_obfuscation = _awg_obfuscation(secrets)

    awg_settings = get_connection_settings("amneziawg")
    awg_server_identity = awg_server_public or str(
        awg_settings.config.get("server_public_key") or ""
    ).strip()
    awg_ipv6_network = (
        _awg_ipv6_network(awg_server_identity)
        if awg_server_identity and _dual_stack_enabled(runtime)
        else None
    )
    xray_settings = get_connection_settings("xray")
    vless_encryption = (
        secrets.get("SG_GATEWAY_VLESS_ENCRYPTION", "").strip()
        or str(xray_settings.config.get("vless_encryption") or "").strip()
    )

    with connect() as connection:
        rows = connection.execute(
            """
            SELECT
                d.id AS client_id,
                CASE WHEN d.is_primary = 1 THEN c.name
                     ELSE c.name || ' · ' || d.name END AS client_name,
                dc.engine,
                dc.engine_object_id,
                dc.config_json
            FROM devices d
            JOIN clients c ON c.id = d.client_id
            JOIN device_credentials dc ON dc.device_id = d.id
            WHERE dc.engine IN ('amneziawg', 'xray')
            ORDER BY d.id, dc.engine
            """
        ).fetchall()

        for row in rows:
            client_id = int(row["client_id"])
            config = _json(row["config_json"])
            engine = str(row["engine"])

            if engine == "amneziawg":
                private_key = str(config.get("private_key") or "").strip()
                public_key = _derive_awg_public(private_key)
                address = _normalise_awg_addresses(
                    client_id,
                    str(config.get("address") or ""),
                    awg_ipv6_network,
                )
                config.update(
                    {
                        "client_name": str(row["client_name"]),
                        "private_key": private_key,
                        "public_key": public_key,
                        "address": address,
                        "dns": awg_settings.config.get("dns", "1.1.1.1"),
                        "server_public_key": awg_server_identity,
                        "endpoint": format_host_port(
                            awg_settings.host or public_address,
                            int(awg_settings.port),
                        ),
                        "allowed_ips": awg_settings.config.get(
                            "allowed_ips",
                            "0.0.0.0/0, ::/0",
                        ),
                        "persistent_keepalive": int(
                            awg_settings.config.get("persistent_keepalive", 25)
                        ),
                        "dual_stack": awg_ipv6_network is not None,
                        "ipv6_network": (
                            str(awg_ipv6_network)
                            if awg_ipv6_network is not None
                            else ""
                        ),
                        **awg_obfuscation,
                    }
                )
                object_id = public_key
            else:
                user_id = str(config.get("uuid") or row["engine_object_id"] or "").strip()
                try:
                    import uuid

                    user_id = str(uuid.UUID(user_id))
                except (ValueError, AttributeError):
                    import uuid

                    user_id = str(uuid.uuid4())

                config.update(
                    {
                        "client_name": str(row["client_name"]),
                        "uuid": user_id,
                        "hysteria_auth": str(config.get("hysteria_auth") or user_id),
                        "host": xray_settings.host or public_address,
                        "port": int(xray_settings.port),
                        "security": "reality",
                        "type": "tcp",
                        "flow": xray_settings.config.get(
                            "flow",
                            "xtls-rprx-vision",
                        ),
                        "fingerprint": xray_settings.config.get(
                            "fingerprint",
                            "firefox",
                        ),
                        "server_name": xray_settings.config.get(
                            "server_name",
                            runtime.get("SG_GATEWAY_REALITY_SNI", "bing.com"),
                        ),
                        "public_key": xray_public
                        or xray_settings.config.get("public_key", ""),
                        "short_id": xray_short_id
                        or xray_settings.config.get("short_id", ""),
                        "vless_encryption": vless_encryption,
                    }
                )
                object_id = user_id

            connection.execute(
                """
                UPDATE device_credentials
                SET engine_object_id = ?,
                    config_json = ?
                WHERE device_id = ? AND engine = ?
                """,
                (
                    object_id,
                    json.dumps(config, ensure_ascii=False, sort_keys=True),
                    client_id,
                    engine,
                ),
            )


def _default_interface() -> str:
    result = _run(["ip", "-4", "route", "show", "default"], timeout=20)
    match = re.search(r"\bdev\s+(\S+)", result.stdout)
    if not match:
        raise ClientRuntimeError("Не удалось определить внешний интерфейс сервера")
    return match.group(1)


def _render_awg_config(rows) -> str:
    secrets = _read_env(ENGINE_SECRETS)
    runtime = _read_env(RUNTIME_ENV)
    server_private = secrets.get("SG_GATEWAY_AWG_PRIVATE_KEY", "").strip()
    server_public = secrets.get("SG_GATEWAY_AWG_PUBLIC_KEY", "").strip()
    if not server_private:
        raise ClientRuntimeError("Не найден серверный приватный ключ AmneziaWG")

    settings = get_connection_settings("amneziawg")
    obfuscation = _awg_obfuscation(secrets)
    external_interface = _default_interface()
    server_identity = server_public or str(
        settings.config.get("server_public_key") or ""
    ).strip()
    ipv6_network = (
        _awg_ipv6_network(server_identity)
        if server_identity and _dual_stack_enabled(runtime)
        else None
    )
    server_address = "10.66.0.1/16"
    if ipv6_network is not None:
        server_ipv6 = ipaddress.IPv6Address(int(ipv6_network.network_address) + 1)
        server_address = f"{server_address}, {server_ipv6}/64"

    post_up = (
        "PostUp = "
        "nft delete table ip sg_gateway_awg 2>/dev/null || true; "
        "nft add table ip sg_gateway_awg; "
        "nft 'add chain ip sg_gateway_awg forward "
        "{ type filter hook forward priority filter; policy accept; }'; "
        "nft 'add chain ip sg_gateway_awg postrouting "
        "{ type nat hook postrouting priority srcnat; policy accept; }'; "
        f'nft add rule ip sg_gateway_awg postrouting '
        f'oifname "{external_interface}" ip saddr 10.66.0.0/16 masquerade'
    )
    post_down = (
        "PostDown = "
        "nft delete table ip sg_gateway_awg 2>/dev/null || true"
    )
    if ipv6_network is not None:
        post_up += (
            "; nft delete table ip6 sg_gateway_awg 2>/dev/null || true; "
            "nft add table ip6 sg_gateway_awg; "
            "nft 'add chain ip6 sg_gateway_awg forward "
            "{ type filter hook forward priority filter; policy accept; }'; "
            "nft 'add chain ip6 sg_gateway_awg postrouting "
            "{ type nat hook postrouting priority srcnat; policy accept; }'; "
            f'nft add rule ip6 sg_gateway_awg postrouting '
            f'oifname "{external_interface}" ip6 saddr {ipv6_network} masquerade'
        )
        post_down += "; nft delete table ip6 sg_gateway_awg 2>/dev/null || true"

    lines = [
        "[Interface]",
        f"Address = {server_address}",
        f"ListenPort = {int(settings.port)}",
        f"PrivateKey = {server_private}",
        f"Jc = {obfuscation['jc']}",
        f"Jmin = {obfuscation['jmin']}",
        f"Jmax = {obfuscation['jmax']}",
        f"S1 = {obfuscation['s1']}",
        f"S2 = {obfuscation['s2']}",
        f"H1 = {obfuscation['h1']}",
        f"H2 = {obfuscation['h2']}",
        f"H3 = {obfuscation['h3']}",
        f"H4 = {obfuscation['h4']}",
        post_up,
        post_down,
        "",
    ]

    for row in rows:
        config = _json(row["config_json"])
        public_key = str(config.get("public_key") or "").strip()
        address = _normalise_awg_addresses(
            int(row["client_id"]),
            str(config.get("address") or ""),
            ipv6_network,
        )
        allowed_ips = _peer_allowed_ips(address)
        if not public_key:
            raise ClientRuntimeError(
                f"AmneziaWG: отсутствует public key клиента {row['client_name']}"
            )
        lines.extend(
            [
                "[Peer]",
                f"# {row['client_name']} · client {row['client_id']}",
                f"PublicKey = {public_key}",
                f"AllowedIPs = {allowed_ips}",
                "",
            ]
        )

    return "\n".join(lines).rstrip() + "\n"


def _apply_awg() -> EngineResult:
    engine = "amneziawg"
    rows = _deployment_rows(engine)
    ids = [int(row["client_id"]) for row in rows]
    previous = _status_snapshot(engine)

    if not rows:
        # Отсутствие клиентов — нормальное состояние новой установки.
        # systemctl stop может вернуть ненулевой код для уже неактивной службы;
        # важен только фактический итоговый статус.
        subprocess.run(
            ["systemctl", "stop", AWG_SERVICE],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        inactive = not _command_ok(
            ["systemctl", "is-active", "--quiet", AWG_SERVICE],
            30,
        )
        if not inactive:
            return EngineResult(
                engine,
                False,
                "AmneziaWG: runtime остался активен без клиентов",
                0,
            )
        return EngineResult(engine, True, "Нет активных клиентов AmneziaWG", 0)

    candidate = CANDIDATE_DIR / "awg0.conf"
    backup = AWG_CONFIG.with_suffix(".conf.previous")
    try:
        _set_engine_status(engine, ids, "checking")
        body = _render_awg_config(rows)
        _atomic_write(candidate, body, 0o600)

        _run(["awg-quick", "strip", str(candidate)], timeout=30)
        _set_engine_status(engine, ids, "applying")

        AWG_CONFIG.parent.mkdir(parents=True, exist_ok=True)
        if AWG_CONFIG.is_file():
            shutil.copy2(AWG_CONFIG, backup)
        _atomic_write(AWG_CONFIG, body, 0o600)

        _atomic_write(
            Path("/etc/sysctl.d/99-sg-gateway-forwarding.conf"),
            "net.ipv4.ip_forward=1\nnet.ipv6.conf.all.forwarding=1\n",
            0o644,
        )
        _run(["sysctl", "--system"], timeout=60)
        _run(["systemctl", "daemon-reload"])
        _run(["systemctl", "enable", AWG_SERVICE])
        _run(["systemctl", "restart", AWG_SERVICE], timeout=90)
        _run(["systemctl", "is-active", "--quiet", AWG_SERVICE])

        _set_engine_status(engine, ids, "applied")
        return EngineResult(
            engine,
            True,
            f"AmneziaWG применён; клиентов: {len(rows)}",
            len(rows),
        )
    except Exception as exc:
        if backup.is_file():
            shutil.copy2(backup, AWG_CONFIG)
            subprocess.run(
                ["systemctl", "restart", AWG_SERVICE],
                capture_output=True,
                text=True,
                check=False,
            )
        restored = _awg_runtime_valid()
        _set_failure_status(
            engine,
            ids,
            previous,
            runtime_restored=restored,
        )
        return EngineResult(engine, False, f"AmneziaWG: {exc}", len(rows))


def _set_xray_config_permissions() -> None:
    # SG_GATEWAY_02111_XRAY_FULL_ACCESS_POLICY
    gid = _xray_service_group_gid()
    os.chown(XRAY_CONFIG, 0, gid)
    os.chmod(XRAY_CONFIG, 0o777)
    if XRAY_CONFIG.parent.is_dir():
        os.chmod(XRAY_CONFIG.parent, 0o777)


def _sync_xray_tls_material(domain: str) -> tuple[str, str]:
    source_dir = LETSENCRYPT_LIVE_ROOT / domain
    source_cert = source_dir / "fullchain.pem"
    source_key = source_dir / "privkey.pem"
    if not source_cert.is_file() or not source_key.is_file():
        raise ClientRuntimeError(
            f"Не найдены файлы TLS-сертификата для {domain}"
        )

    gid = _xray_service_group_gid()
    XRAY_TLS_DIR.mkdir(parents=True, exist_ok=True)
    os.chown(XRAY_TLS_DIR, 0, gid)
    os.chmod(XRAY_TLS_DIR, 0o777)

    for source, target in (
        (source_cert, XRAY_TLS_CERT),
        (source_key, XRAY_TLS_KEY),
    ):
        temporary = target.with_name(target.name + ".new")
        with source.open("rb") as source_handle, temporary.open("wb") as target_handle:
            shutil.copyfileobj(source_handle, target_handle)
            target_handle.flush()
            os.fsync(target_handle.fileno())
        os.chown(temporary, 0, gid)
        os.chmod(temporary, 0o777)
        os.replace(temporary, target)

    return str(XRAY_TLS_CERT), str(XRAY_TLS_KEY)


def _live_hysteria_finalmask_base(previous_config: dict[str, Any]) -> dict[str, Any]:
    """Return unmanaged FinalMask layers from the current live Hysteria2 inbound."""
    try:
        payload = json.loads(XRAY_CONFIG.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict) or not isinstance(payload.get("inbounds"), list):
        return {}
    finalmask: dict[str, Any] = {}
    for inbound in payload["inbounds"]:
        if not isinstance(inbound, dict) or inbound.get("tag") != "sg-hysteria2":
            continue
        stream = inbound.get("streamSettings")
        if isinstance(stream, dict) and isinstance(stream.get("finalmask"), dict):
            finalmask = copy.deepcopy(stream["finalmask"])
        break
    if not finalmask:
        return {}

    previous_mode = str(previous_config.get("hysteria2_obfs_mode") or "none").strip().lower()
    previous_password = str(previous_config.get("hysteria2_obfs_password") or "")
    if previous_mode == "salamander" and previous_password:
        udp = finalmask.get("udp")
        if isinstance(udp, list):
            filtered = []
            removed = False
            for item in udp:
                is_managed = (
                    not removed
                    and isinstance(item, dict)
                    and str(item.get("type") or "").strip().lower() == "salamander"
                    and isinstance(item.get("settings"), dict)
                    and str(item["settings"].get("password") or "") == previous_password
                )
                if is_managed:
                    removed = True
                    continue
                filtered.append(item)
            if filtered:
                finalmask["udp"] = filtered
            else:
                finalmask.pop("udp", None)
    return finalmask


def _preserve_live_hysteria_finalmask(settings, settings_config: dict[str, Any]) -> dict[str, Any]:
    stored = settings_config.get("hysteria2_finalmask")
    if isinstance(stored, dict) and stored:
        return settings_config
    transaction = pending_settings_transaction("xray")
    previous_config = transaction.previous_config if transaction is not None else settings_config
    discovered = _live_hysteria_finalmask_base(previous_config)
    if not discovered:
        return settings_config
    updated = dict(settings_config)
    updated["hysteria2_finalmask"] = discovered
    if transaction is not None:
        update_settings_candidate_config(transaction.id, updated)
    else:
        update_connection_settings("xray", settings.host, settings.port, updated)
    return updated


def _render_xray_config(rows) -> str:
    secrets = _read_env(ENGINE_SECRETS)
    runtime = _read_env(RUNTIME_ENV)
    private_key = secrets.get("SG_GATEWAY_XRAY_PRIVATE_KEY", "").strip()
    short_id = secrets.get("SG_GATEWAY_XRAY_SHORT_ID", "").strip()
    vless_decryption = secrets.get("SG_GATEWAY_VLESS_DECRYPTION", "").strip()
    raw_vless_encryption = secrets.get("SG_GATEWAY_VLESS_ENCRYPTION", "").strip()
    if raw_vless_encryption or vless_decryption:
        try:
            _client_encryption, vless_decryption, _swapped = normalize_pair(
                raw_vless_encryption, vless_decryption
            )
        except VlessEncryptionError as exc:
            raise ClientRuntimeError(str(exc)) from exc
    if not private_key or not short_id:
        raise ClientRuntimeError("Не найдены серверные ключи Xray Reality")

    settings = get_connection_settings("xray")
    settings_config = _preserve_live_hysteria_finalmask(settings, dict(settings.config))
    profiles = xray_profiles_overview()
    by_id = {item.id: item for item in profiles["profiles"]}
    enabled_profiles = {
        item.id for item in profiles["profiles"] if item.enabled
    }
    if {"xhttp_reality", "xhttp_tls"} & enabled_profiles:
        if not vless_decryption:
            raise ClientRuntimeError(
                "Не найден серверный ключ VLESS Encryption. "
                "Повторите установку текущей версии SG-Gateway."
            )
    server_name = str(
        settings_config.get("server_name")
        or runtime.get("SG_GATEWAY_REALITY_SNI")
        or "bing.com"
    ).strip()
    target = str(
        settings_config.get("target")
        or runtime.get("SG_GATEWAY_REALITY_TARGET")
        or "bing.com:443"
    ).strip()
    public_listen = "::" if _dual_stack_enabled(runtime) else "0.0.0.0"

    grouped: dict[str, list[dict[str, Any]]] = {
        "reality_tcp": [],
        "xhttp_reality": [],
        "xhttp_tls": [],
        "hysteria2": [],
    }
    for row in rows:
        config = _json(row["config_json"])
        user_id = str(config.get("uuid") or row["engine_object_id"] or "").strip()
        if not user_id:
            raise ClientRuntimeError(
                f"Xray: отсутствует UUID клиента {row['client_name']}"
            )
        selected = config.get("profiles")
        if not isinstance(selected, list) or not selected:
            selected = ["reality_tcp", "xhttp_reality"]
        email = f"sg-client-{row['client_id']}@sg-gateway"
        for profile_id in [str(item) for item in selected]:
            if profile_id not in grouped:
                continue
            profile = by_id.get(profile_id)
            if profile is None or not profile.enabled:
                raise ClientRuntimeError(
                    f"Xray-профиль {profile_id} выбран у клиента "
                    f"{row['client_name']}, но выключен на сервере"
                )
            if profile.tls_required and not profile.ready:
                raise ClientRuntimeError(
                    f"Xray-профиль {profile.title} требует готового HTTPS"
                )
            if profile_id == "hysteria2":
                grouped[profile_id].append(
                    {"auth": str(config.get("hysteria_auth") or user_id), "email": email, "level": 0}
                )
            elif profile_id in {"reality_tcp", "xhttp_reality", "xhttp_tls"}:
                grouped[profile_id].append(
                    {"id": user_id, "email": email, "flow": REALITY_TCP_FLOW}
                )
            else:
                grouped[profile_id].append({"id": user_id, "email": email})

    sniffing = {
        "enabled": True,
        "destOverride": ["http", "tls", "quic"],
        "routeOnly": True,
    }
    inbounds: list[dict[str, Any]] = []

    if "reality_tcp" in enabled_profiles:
        profile = by_id["reality_tcp"]
        # SG_GATEWAY_PLACEHOLDER_80_443_V1
        inbound = reality_tcp_inbound(
            clients=grouped["reality_tcp"],
            port=int(runtime.get("SG_GATEWAY_REALITY_INTERNAL_PORT") or 7443),
            listen="127.0.0.1",
            dest=target,
            server_name=server_name,
            private_key=private_key,
            short_id=short_id,
        )
        inbound["sniffing"] = sniffing
        inbounds.append(inbound)

    if "xhttp_reality" in enabled_profiles:
        profile = by_id["xhttp_reality"]
        inbound = xhttp_reality_inbound(
            clients=grouped["xhttp_reality"],
            port=profile.port,
            path=profile.path,
            decryption=vless_decryption,
            dest=target,
            server_name=server_name,
            private_key=private_key,
            short_id=short_id,
            listen=public_listen,
        )
        inbound["sniffing"] = sniffing
        inbounds.append(inbound)

    tls_needed = bool({"xhttp_tls", "hysteria2"} & enabled_profiles)
    if tls_needed:
        if not profiles.get("tls_ready") or not profiles.get("tls_domain"):
            raise ClientRuntimeError(
                "Xray TLS-профили выбраны, но HTTPS в Security не готов"
            )
        domain = str(profiles["tls_domain"])
        cert, key = _sync_xray_tls_material(domain)
        tls_settings = {
            "serverName": domain,
            "minVersion": "1.2",
            "alpn": ["h2", "http/1.1"],
            "certificates": [
                {"certificateFile": cert, "keyFile": key}
            ],
        }
        if "xhttp_tls" in enabled_profiles:
            profile = by_id["xhttp_tls"]
            inbounds.append({
                "tag": "sg-vless-xhttp-tls",
                "listen": public_listen,
                "port": profile.port,
                "protocol": "vless",
                "settings": {
                    "clients": grouped["xhttp_tls"],
                    "decryption": vless_decryption,
                },
                "streamSettings": {
                    "network": "xhttp",
                    "security": "tls",
                    "tlsSettings": tls_settings,
                    "xhttpSettings": {"path": profile.path, "mode": "auto"},
                },
                "sniffing": sniffing,
            })
        if "hysteria2" in enabled_profiles:
            profile = by_id["hysteria2"]
            hysteria_tls = dict(tls_settings)
            hysteria_tls["alpn"] = ["h3"]
            hysteria_stream = {
                "network": "hysteria",
                "security": "tls",
                "tlsSettings": hysteria_tls,
                "hysteriaSettings": {
                    "version": 2,
                    "udpIdleTimeout": 60,
                },
            }
            try:
                finalmask = merge_finalmask(
                    settings_config.get("hysteria2_finalmask") or {},
                    settings_config.get("hysteria2_obfs_mode") or "none",
                    settings_config.get("hysteria2_obfs_password") or "",
                )
            except SalamanderError as exc:
                raise ClientRuntimeError(str(exc)) from exc
            if finalmask:
                hysteria_stream["finalmask"] = finalmask
            inbounds.append({
                "tag": "sg-hysteria2",
                "listen": public_listen,
                "port": profile.port,
                "protocol": "hysteria",
                "settings": {
                    "version": 2,
                    "users": grouped["hysteria2"],
                },
                "streamSettings": hysteria_stream,
                "sniffing": sniffing,
            })

    if not inbounds:
        raise ClientRuntimeError("У активных клиентов не выбран ни один Xray-профиль")

    outbounds = [{"tag": "direct", "protocol": "freedom"}]
    try:
        from app.routing.warp import outbound as warp_outbound

        warp = warp_outbound(require_enabled=True)
        if warp is not None:
            outbounds.append(warp)
    except ImportError:
        pass
    except Exception as exc:
        raise ClientRuntimeError(str(exc)) from exc
    outbounds.append({"tag": "block", "protocol": "blackhole"})

    payload = {
        "log": {"loglevel": "warning"},
        "inbounds": inbounds,
        "outbounds": outbounds,
        "routing": _load_managed_routing(),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def test_xray_candidate() -> dict[str, Any]:
    """Render and validate the selected server profiles without applying them."""
    rows = _deployment_rows("xray")
    candidate = CANDIDATE_DIR / "xray-config.test.json"
    try:
        _require_xray_version()
        body = _render_xray_config(rows)
        _atomic_write(candidate, body, 0o600)
        result = subprocess.run(
            [
                "/usr/local/bin/xray",
                "run",
                "-test",
                "-config",
                str(candidate),
            ],
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
        )
    except (OSError, subprocess.SubprocessError, ClientRuntimeError) as exc:
        return {
            "ok": False,
            "message": str(exc),
            "candidate": str(candidate),
            "clients": len(rows),
        }

    output = (result.stdout or result.stderr or "").strip()
    if result.returncode == 0:
        suffix = (
            f"; клиентов в candidate: {len(rows)}"
            if rows
            else "; профили проверены без клиентских записей"
        )
        message = (output or "Xray candidate корректен") + suffix
    else:
        message = output or "Xray candidate не прошёл проверку"
    return {
        "ok": result.returncode == 0,
        "message": message,
        "candidate": str(candidate),
        "clients": len(rows),
    }


def _apply_xray(*, force_profiles: bool = False) -> EngineResult:
    engine = "xray"
    settings_transaction = pending_settings_transaction(engine)
    rows = _deployment_rows(engine)
    ids = [int(row["client_id"]) for row in rows]
    previous = _status_snapshot(engine)

    if not rows and settings_transaction is None and not force_profiles:
        # Disabling or deleting the last Xray client is a valid catalogue
        # operation. Keep the last tested config for a future re-enable, but
        # stop the service so no disabled UUID remains reachable.
        subprocess.run(
            ["systemctl", "stop", "xray.service"],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        inactive = not _command_ok(
            ["systemctl", "is-active", "--quiet", "xray.service"],
            30,
        )
        if not inactive:
            if settings_transaction is not None:
                rollback_settings_transaction(
                    settings_transaction.id, status="rolled_back_service_stop_error"
                )
            return EngineResult(
                engine,
                False,
                "Xray: служба осталась активной без разрешённых клиентов",
                0,
            )
        if settings_transaction is not None:
            commit_settings_transaction(settings_transaction.id)
        return EngineResult(
            engine,
            True,
            "Нет активных Xray-клиентов; служба остановлена",
            0,
        )

    candidate = CANDIDATE_DIR / "xray-config.json"
    backup = XRAY_CONFIG.with_suffix(".json.previous")
    had_live_config = XRAY_CONFIG.is_file()
    try:
        _require_xray_version()
        _set_engine_status(engine, ids, "checking")
        body = _render_xray_config(rows)
        _atomic_write(candidate, body, 0o600)
        _run(
            [
                "/usr/local/bin/xray",
                "run",
                "-test",
                "-config",
                str(candidate),
            ],
            timeout=60,
        )
        _set_engine_status(engine, ids, "applying")

        XRAY_CONFIG.parent.mkdir(parents=True, exist_ok=True)
        if backup.exists():
            backup.unlink()
        if had_live_config:
            shutil.copy2(XRAY_CONFIG, backup)
        _atomic_write(XRAY_CONFIG, body, 0o600)
        _set_xray_config_permissions()

        _run(["systemctl", "daemon-reload"])
        _run(["systemctl", "enable", "xray.service"])
        _run(["systemctl", "restart", "xray.service"], timeout=90)
        _run(["systemctl", "is-active", "--quiet", "xray.service"])

        current_profiles = xray_profiles_overview()
        hysteria_profile = next(
            (item for item in current_profiles["profiles"] if item.id == "hysteria2"),
            None,
        )
        if hysteria_profile is not None and hysteria_profile.enabled:
            deadline = time.monotonic() + 10.0
            while not _udp_port_listening(hysteria_profile.port):
                if time.monotonic() >= deadline:
                    raise ClientRuntimeError(
                        f"Hysteria2 UDP-порт {hysteria_profile.port} не слушается через 10 секунд после запуска Xray"
                    )
                time.sleep(0.25)

        if settings_transaction is not None:
            change_message = _salamander_change_message(settings_transaction)
            commit_settings_transaction(settings_transaction.id)
            if change_message:
                log_operation(
                    action="xray.hysteria2.salamander",
                    target="inbound:sg-hysteria2",
                    message=change_message,
                )

        _set_engine_status(engine, ids, "applied")
        return EngineResult(
            engine,
            True,
            f"Xray-профили применены; клиентов: {len(rows)}",
            len(rows),
        )
    except Exception as exc:
        if backup.is_file():
            shutil.copy2(backup, XRAY_CONFIG)
            _set_xray_config_permissions()
            subprocess.run(
                ["systemctl", "restart", "xray.service"],
                capture_output=True,
                text=True,
                check=False,
            )
        elif not had_live_config:
            XRAY_CONFIG.unlink(missing_ok=True)
            subprocess.run(
                ["systemctl", "stop", "xray.service"],
                capture_output=True,
                text=True,
                check=False,
            )
        if settings_transaction is not None:
            rollback_settings_transaction(settings_transaction.id, status="rolled_back_runtime_error")
        restored = _xray_runtime_valid()
        _set_failure_status(
            engine,
            ids,
            previous,
            runtime_restored=restored,
        )
        return EngineResult(engine, False, f"Xray Reality: {exc}", len(rows))


def _apply_mihomo() -> EngineResult:
    engine = "mihomo"
    rows = _deployment_rows(engine)
    ids = [int(row["client_id"]) for row in rows]
    previous = _status_snapshot(engine)

    if not rows:
        # Mihomo is a permanent SG-Gateway runtime.  With no Mieru clients it
        # stays active on a valid listener-free configuration instead of being
        # stopped.  The first client replaces this idle config transactionally.
        idle_config = Path("/etc/mihomo/config.yaml")
        idle_body = (
            "mode: rule\n"
            "log-level: warning\n"
            "listeners: []\n"
            "proxies: []\n"
            "proxy-groups: []\n"
            "rules: []\n"
        )
        try:
            idle_config.parent.mkdir(parents=True, exist_ok=True)
            _atomic_write(idle_config, idle_body, 0o600)
            _run(["/usr/local/bin/mihomo", "-t", "-f", str(idle_config)], timeout=60)
            _run(["systemctl", "enable", "mihomo.service"])
            _run(["systemctl", "restart", "mihomo.service"], timeout=90)
            _run(["systemctl", "is-active", "--quiet", "mihomo.service"], timeout=30)
        except Exception as exc:
            return EngineResult(engine, False, f"Mihomo idle runtime: {exc}", 0)
        return EngineResult(engine, True, "Mihomo runtime готов; активных клиентов нет", 0)

    try:
        _set_engine_status(engine, ids, "checking")
        from app.mihomo.helper import apply_candidate

        # Candidate files belong to the unprivileged panel side.  Never build
        # them as root: otherwise the next web request cannot replace them.
        _run(
            [
                "runuser",
                "-u",
                "sg-gateway",
                "--",
                "env",
                f"PYTHONPATH={PREFIX}",
                str(PREFIX / ".venv/bin/python"),
                "-c",
                "from app.mihomo.service import build_candidate; build_candidate()",
            ],
            timeout=60,
        )
        _set_engine_status(engine, ids, "applying")
        result = apply_candidate()
        if not result.get("ok"):
            raise ClientRuntimeError(str(result.get("message") or "Mihomo apply failed"))

        _set_engine_status(engine, ids, "applied")
        return EngineResult(
            engine,
            True,
            str(result.get("message") or f"Mihomo применён; клиентов: {len(rows)}"),
            len(rows),
        )
    except Exception as exc:
        restored = _mihomo_runtime_valid()
        _set_failure_status(
            engine,
            ids,
            previous,
            runtime_restored=restored,
        )
        return EngineResult(engine, False, f"Mihomo/Mieru: {exc}", len(rows))

def _singbox_binary() -> str:
    for candidate in ("/usr/bin/sing-box", "/usr/local/bin/sing-box"):
        if Path(candidate).is_file():
            return candidate
    resolved = shutil.which("sing-box")
    if not resolved:
        raise ClientRuntimeError("sing-box не установлен")
    return resolved


def _singbox_runtime_valid() -> bool:
    try:
        binary = _singbox_binary()
    except ClientRuntimeError:
        return False
    return bool(
        SINGBOX_CONFIG.is_file()
        and _command_ok([binary, "check", "-c", str(SINGBOX_CONFIG)], 60)
        and _command_ok(
            ["systemctl", "is-active", "--quiet", SINGBOX_SERVICE],
            30,
        )
    )


def _render_singbox_config(anytls_rows, tuic_rows, settings: dict[str, Any]) -> str:
    tls = tls_overview()
    domain = str(tls.get("domain") or "").strip()
    if not tls.get("https_ready") or not domain:
        raise ClientRuntimeError(
            "AnyTLS и TUIC v5 требуют настроенного HTTPS в Security"
        )
    cert = f"/etc/letsencrypt/live/{domain}/fullchain.pem"
    key = f"/etc/letsencrypt/live/{domain}/privkey.pem"
    if not Path(cert).is_file() or not Path(key).is_file():
        raise ClientRuntimeError("Не найдены файлы TLS-сертификата")

    inbounds: list[dict[str, Any]] = []
    if anytls_rows:
        users = []
        port = int(settings.get("anytls_port") or 9443)
        for row in anytls_rows:
            config = _json(row["config_json"])
            password = str(config.get("password") or "").strip()
            if not password:
                raise ClientRuntimeError(
                    f"AnyTLS: отсутствует пароль клиента {row['client_name']}"
                )
            users.append({
                "name": f"client-{row['client_id']}",
                "password": password,
            })
        inbounds.append({
            "type": "anytls",
            "tag": "sg-anytls-in",
            "listen": "::",
            "listen_port": port,
            "users": users,
            "tls": {
                "enabled": True,
                "server_name": domain,
                "certificate_path": cert,
                "key_path": key,
            },
        })

    if tuic_rows:
        users = []
        port = int(settings.get("tuic_port") or 10443)
        for row in tuic_rows:
            config = _json(row["config_json"])
            user_id = str(config.get("uuid") or row["engine_object_id"] or "").strip()
            password = str(config.get("password") or "").strip()
            if not user_id or not password:
                raise ClientRuntimeError(
                    f"TUIC v5: отсутствуют credentials клиента {row['client_name']}"
                )
            users.append({
                "name": f"client-{row['client_id']}",
                "uuid": user_id,
                "password": password,
            })
        inbounds.append({
            "type": "tuic",
            "tag": "sg-tuic-in",
            "listen": "::",
            "listen_port": port,
            "users": users,
            "congestion_control": str(settings.get("tuic_congestion_controller") or "bbr"),
            "zero_rtt_handshake": False,
            "tls": {
                "enabled": True,
                "server_name": domain,
                "alpn": [str(settings.get("tuic_alpn") or "h3")],
                "certificate_path": cert,
                "key_path": key,
            },
        })

    if not inbounds:
        raise ClientRuntimeError("Нет активных клиентов AnyTLS или TUIC v5")
    payload = {
        "log": {"level": "warn", "timestamp": True},
        "inbounds": inbounds,
        "outbounds": [{"type": "direct", "tag": "direct"}],
        "route": {"final": "direct"},
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def _sync_singbox_client_configs(settings: dict[str, Any], anytls_rows, tuic_rows) -> None:
    """Commit server endpoint settings to client exports only after runtime succeeds."""
    tls = tls_overview()
    domain = str(tls.get("domain") or "").strip()
    with connect() as connection:
        for engine, rows in (("anytls", anytls_rows), ("tuic", tuic_rows)):
            for row in rows:
                config = _json(row["config_json"])
                config["host"] = domain
                config["server_name"] = domain
                if engine == "anytls":
                    config["port"] = int(settings.get("anytls_port") or 9443)
                else:
                    config["port"] = int(settings.get("tuic_port") or 10443)
                    config["congestion_control"] = str(settings.get("tuic_congestion_controller") or "bbr")
                    config["udp_relay_mode"] = str(settings.get("tuic_udp_relay_mode") or "native")
                    config["alpn"] = str(settings.get("tuic_alpn") or "h3")
                connection.execute(
                    """
                    UPDATE device_credentials
                    SET config_json = ?
                    WHERE device_id = ? AND engine = ?
                    """,
                    (json.dumps(config, ensure_ascii=False, sort_keys=True), int(row["client_id"]), engine),
                )


def _apply_singbox() -> list[EngineResult]:
    server = get_connection_settings("mihomo")
    settings = dict(server.config)
    anytls_enabled = bool(settings.get("anytls_enabled"))
    tuic_enabled = bool(settings.get("tuic_enabled"))
    anytls_rows = _deployment_rows("anytls") if anytls_enabled else []
    tuic_rows = _deployment_rows("tuic") if tuic_enabled else []
    rows_by_engine = {"anytls": anytls_rows, "tuic": tuic_rows}
    ids_by_engine = {
        engine: [int(row["client_id"]) for row in rows]
        for engine, rows in rows_by_engine.items()
    }
    previous = {
        engine: _status_snapshot(engine)
        for engine in rows_by_engine
    }
    total_rows = len(anytls_rows) + len(tuic_rows)

    if total_rows == 0:
        subprocess.run(
            ["systemctl", "stop", SINGBOX_SERVICE],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        inactive = not _command_ok(
            ["systemctl", "is-active", "--quiet", SINGBOX_SERVICE], 30
        )
        ok = inactive
        suffix = "не выбраны" if ok else "служба осталась активной"
        return [
            EngineResult("anytls", ok, f"AnyTLS: {suffix}", 0),
            EngineResult("tuic", ok, f"TUIC v5: {suffix}", 0),
        ]

    all_ids = ids_by_engine["anytls"] + ids_by_engine["tuic"]
    candidate = CANDIDATE_DIR / "sing-box-config.json"
    backup = SINGBOX_CONFIG.with_suffix(".json.previous")
    try:
        for engine, ids in ids_by_engine.items():
            _set_engine_status(engine, ids, "checking")
        body = _render_singbox_config(anytls_rows, tuic_rows, settings)
        _atomic_write(candidate, body, 0o600)
        binary = _singbox_binary()
        _run([binary, "check", "-c", str(candidate)], timeout=60)
        for engine, ids in ids_by_engine.items():
            _set_engine_status(engine, ids, "applying")

        SINGBOX_CONFIG.parent.mkdir(parents=True, exist_ok=True)
        if SINGBOX_CONFIG.is_file():
            shutil.copy2(SINGBOX_CONFIG, backup)
        _atomic_write(SINGBOX_CONFIG, body, 0o600)
        _run(["systemctl", "daemon-reload"])
        _run(["systemctl", "enable", SINGBOX_SERVICE])
        _run(["systemctl", "restart", SINGBOX_SERVICE], timeout=90)
        _run(["systemctl", "is-active", "--quiet", SINGBOX_SERVICE])
        _sync_singbox_client_configs(settings, anytls_rows, tuic_rows)
        for engine, ids in ids_by_engine.items():
            _set_engine_status(engine, ids, "applied")
        return [
            EngineResult(
                "anytls", True,
                f"AnyTLS применён; клиентов: {len(anytls_rows)}",
                len(anytls_rows),
            ),
            EngineResult(
                "tuic", True,
                f"TUIC v5 применён; клиентов: {len(tuic_rows)}",
                len(tuic_rows),
            ),
        ]
    except Exception as exc:
        if backup.is_file():
            shutil.copy2(backup, SINGBOX_CONFIG)
            subprocess.run(
                ["systemctl", "restart", SINGBOX_SERVICE],
                capture_output=True,
                text=True,
                check=False,
            )
        restored = _singbox_runtime_valid()
        for engine, ids in ids_by_engine.items():
            _set_failure_status(
                engine,
                ids,
                previous[engine],
                runtime_restored=restored,
            )
        return [
            EngineResult(
                "anytls", False, f"AnyTLS: {exc}", len(anytls_rows)
            ),
            EngineResult(
                "tuic", False, f"TUIC v5: {exc}", len(tuic_rows)
            ),
        ]

def _apply_sgclient() -> EngineResult:
    engine = "sgclient"
    rows = _deployment_rows(engine)
    ids = [int(row["client_id"]) for row in rows]
    if not rows:
        return EngineResult(engine, True, "SG Client не выбран", 0)

    _set_engine_status(engine, ids, "checking")
    applied = 0
    failed = 0
    with connect() as connection:
        for row in rows:
            client_id = int(row["client_id"])
            sources = connection.execute(
                """
                SELECT engine, status, config_json
                FROM device_credentials
                WHERE device_id = ? AND engine IN ('xray', 'mihomo', 'anytls', 'tuic')
                """,
                (client_id,),
            ).fetchall()
            ready = [
                item for item in sources
                if str(item["status"]) == "applied" and bool(_json(item["config_json"]))
            ]
            connection.execute(
                """
                UPDATE device_credentials
                SET status = 'applying'
                WHERE device_id = ? AND engine = 'sgclient'
                """,
                (client_id,),
            )
            status = "applied" if ready else "error"
            connection.execute(
                """
                UPDATE device_credentials
                SET status = ?
                WHERE device_id = ? AND engine = 'sgclient'
                """,
                (status, client_id),
            )
            if ready:
                applied += 1
            else:
                failed += 1

    if failed:
        return EngineResult(
            engine,
            False,
            f"SG Client: подписок готово {applied}, ошибок {failed}",
            len(rows),
        )
    return EngineResult(
        engine,
        True,
        f"SG Client subscription сформирована; клиентов: {applied}",
        len(rows),
    )


def apply_xray_runtime(*, force_profiles: bool = False) -> dict[str, Any]:
    """Migrate Xray deployment data, validate the candidate, and apply it."""
    init_db()
    CANDIDATE_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(CANDIDATE_DIR, 0o750)
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    transaction = pending_settings_transaction("xray")
    try:
        with LOCK_FILE.open("a+", encoding="utf-8") as lock_handle:
            try:
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise ClientRuntimeError(
                    "Другое применение клиентских конфигураций уже выполняется"
                ) from exc
            _repair_deployment_configs()
            rows = _deployment_rows("xray")
            if not rows and transaction is None and not force_profiles:
                # An update may legitimately have no Xray deployments yet.
                # Do not replace or restart an existing runtime with an empty
                # generated config; the first client apply will build it.
                return {
                    "ok": True,
                    "message": (
                        "Нет активных Xray-клиентов; существующая конфигурация "
                        "Xray сохранена"
                    ),
                    "engine": "xray",
                    "clients": 0,
                    "runtime_preserved": True,
                }
            # A pending server-profile transaction is still rendered in full
            # even with zero users, so Xray validates the exact future inbound.
            result = _apply_xray(force_profiles=force_profiles)
        return {
            "ok": result.ok,
            "message": result.message,
            "engine": result.engine,
            "clients": result.clients,
        }
    except Exception:
        current = pending_settings_transaction("xray")
        if current is not None:
            rollback_settings_transaction(
                current.id, status="rolled_back_unhandled_runtime_error"
            )
        raise


def apply_split_mihomo_singbox_runtime() -> dict[str, Any]:
    """Apply the Connections card: Mieru in Mihomo plus AnyTLS/TUIC in sing-box."""
    from app.mihomo.helper import apply_candidate as apply_mihomo_candidate

    mihomo = apply_mihomo_candidate()
    if not mihomo.get("ok"):
        raise ClientRuntimeError(str(mihomo.get("message") or "Mihomo apply failed"))
    singbox = _apply_singbox()
    failed = [item for item in singbox if not item.ok]
    messages = [str(mihomo.get("message") or "Mieru применён")] + [item.message for item in singbox]
    if failed:
        return {
            "ok": False,
            "message": "; ".join(messages),
            "engines": {item.engine: item.ok for item in singbox},
        }
    return {
        "ok": True,
        "message": "; ".join(messages),
        "engines": {"mihomo": True, **{item.engine: item.ok for item in singbox}},
    }


def apply_all_clients() -> dict[str, Any]:
    """Apply critical engines and report optional engines independently.

    Client catalogue operations are committed when selected AWG2/AWG3 and Xray are
    healthy. Mieru, AnyTLS, TUIC and SG Client exports remain visible in the
    result, but an optional engine can no longer roll back a client create,
    update, delete or the whole SG-Gateway installation.
    """
    init_db()
    CANDIDATE_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(CANDIDATE_DIR, 0o750)
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)

    with LOCK_FILE.open("a+", encoding="utf-8") as lock_handle:
        try:
            fcntl.flock(
                lock_handle.fileno(),
                fcntl.LOCK_EX | fcntl.LOCK_NB,
            )
        except BlockingIOError as exc:
            raise ClientRuntimeError(
                "Другое применение клиентских конфигураций уже выполняется"
            ) from exc

        _repair_deployment_configs()

        from sg_hostd.awg3_runtime import apply_awg3

        critical_results = [
            _apply_awg(),
            apply_awg3(),
            _apply_xray(),
        ]
        optional_results = [
            _apply_mihomo(),
        ]
        optional_results.extend(_apply_singbox())
        optional_results.append(_apply_sgclient())

        results = critical_results + optional_results
        ok = all(result.ok for result in critical_results)
        warnings = [
            result.message
            for result in optional_results
            if not result.ok
        ]

        message = "; ".join(result.message for result in results)
        if warnings:
            message += (
                "; Необязательные компоненты требуют внимания: "
                + " | ".join(warnings)
            )

        operation_status = (
            "ok"
            if ok and not warnings
            else ("warning" if ok else "error")
        )
        log_operation(
            action="clients.runtime.apply",
            target="clients:all",
            status=operation_status,
            message=message,
        )

        return {
            "ok": ok,
            "message": message,
            "warnings": warnings,
            "engines": [
                {
                    "engine": result.engine,
                    "ok": result.ok,
                    "message": result.message,
                    "clients": result.clients,
                    "critical": result in critical_results,
                }
                for result in results
            ],
        }
