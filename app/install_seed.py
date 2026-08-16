from __future__ import annotations

import json
import os
from typing import Any

from app.connections.settings import get_connection_settings, update_connection_settings
from app.clients.repository import count_clients, create_client
from app.constants import AMNEZIAWG3_UDP_PORT, AMNEZIAWG_UDP_PORT
from app.db import connect, init_db

_PLACEHOLDER_PREFIXES = ("PLACEHOLDER_", "CHANGEME", "TODO")


def _text(name: str, default: str = "") -> str:
    return str(os.environ.get(name, default)).strip()


def _port(value: Any, fallback: int) -> int:
    try:
        port = int(value)
    except (TypeError, ValueError):
        return fallback
    return port if 1 <= port <= 65535 else fallback


def _usable(value: Any) -> bool:
    text = str(value or "").strip()
    return bool(text) and not text.upper().startswith(_PLACEHOLDER_PREFIXES)


def _country(config: dict[str, Any], detected: str) -> None:
    if detected and detected != "unknown":
        config["country_code"] = detected


def _save(engine: str, host: str, port: int, config: dict[str, Any]) -> None:
    if not update_connection_settings(engine, host, port, config):
        raise RuntimeError(
            f"Не удалось сохранить {engine}: host={host!r}, port={port!r}"
        )


def _synchronize_xray_credentials(
    *,
    host: str,
    port: int,
    fingerprint: str,
    server_name: str,
    public_key: str,
    short_id: str,
    vless_encryption: str,
) -> int:
    synchronized = 0
    server_values = {
        "host": host,
        "port": int(port),
        "fingerprint": fingerprint,
        "server_name": server_name,
        "public_key": public_key,
        "short_id": short_id,
        "vless_encryption": vless_encryption,
    }
    with connect() as connection:
        rows = connection.execute(
            "SELECT id, config_json FROM device_credentials WHERE engine = 'xray'"
        ).fetchall()
        for row in rows:
            try:
                config = json.loads(row["config_json"] or "{}")
            except (TypeError, ValueError, json.JSONDecodeError):
                config = {}
            if not isinstance(config, dict):
                config = {}
            changed = False
            for key, value in server_values.items():
                if config.get(key) != value:
                    config[key] = value
                    changed = True
            if not changed:
                continue
            connection.execute(
                "UPDATE device_credentials SET config_json = ? WHERE id = ?",
                (
                    json.dumps(config, ensure_ascii=False, sort_keys=True),
                    int(row["id"]),
                ),
            )
            synchronized += 1
    return synchronized


def seed_or_migrate() -> None:
    init_db()

    update_mode = _text("SG_UPDATE_MODE") == "1"
    public_host = _text("SG_SEED_PUBLIC_ADDRESS")
    if not public_host:
        raise RuntimeError("Публичный IP сервера не передан в инициализацию базы")

    country = _text("SG_GATEWAY_COUNTRY_CODE", "unknown").lower()
    vless_encryption = _text("SG_SEED_VLESS_ENCRYPTION")
    xray_public_key = _text("SG_SEED_XRAY_PUBLIC_KEY")
    xray_short_id = _text("SG_SEED_XRAY_SHORT_ID")
    awg_public_key = _text("SG_SEED_AWG_PUBLIC_KEY")

    xray = get_connection_settings("xray")
    xray_config = dict(xray.config)
    xray_host = str(xray.host or "").strip() or public_host
    xray_port = _port(xray.port, _port(_text("SG_SEED_XRAY_PORT"), 443))
    current_reality_mode = str(xray_config.get("xhttp_reality_mode") or "").strip().lower()
    if current_reality_mode in {"", "stream-up"}:
        xray_config["xhttp_reality_mode"] = "stream-one"
    xray_config.setdefault("xhttp_tls_mode", "auto")
    _country(xray_config, country)
    if not _usable(xray_config.get("vless_encryption")):
        xray_config["vless_encryption"] = vless_encryption

    # Reality credentials have exactly one source of truth: the active
    # root-owned engine-secrets.env. A non-empty value in an old/interrupted
    # database is not proof that it belongs to the active private key. Keeping
    # stale public_key/short_id breaks both Reality TCP and XHTTP while Xray
    # configuration still passes syntactic validation. Always synchronize them.
    if not _usable(xray_public_key) or not _usable(xray_short_id):
        raise RuntimeError("Активные ключи Xray Reality не переданы в инициализацию")
    xray_config["public_key"] = xray_public_key
    xray_config["short_id"] = xray_short_id

    if update_mode:
        # Preserve intentional expert transport values, but repair missing
        # endpoint metadata from the current installer answers.
        if not _usable(xray_config.get("server_name")):
            xray_config["server_name"] = _text("SG_SEED_REALITY_SNI")
        if not _usable(xray_config.get("target")):
            xray_config["target"] = _text("SG_SEED_REALITY_TARGET")
    else:
        xray_config.update(
            {
                "vless_encryption": vless_encryption,
                "server_name": _text("SG_SEED_REALITY_SNI"),
                "target": _text("SG_SEED_REALITY_TARGET"),
                "public_key": xray_public_key,
                "short_id": xray_short_id,
                "reality_tcp_enabled": True,
                "reality_tcp_port": _port(_text("SG_SEED_XRAY_PORT"), 443),
                "xhttp_reality_enabled": True,
                "xhttp_reality_port": 8444,
                "xhttp_reality_path": "/sg-xhttp-reality",
                "xhttp_reality_mode": "stream-one",
                "xhttp_tls_enabled": False,
                "xhttp_tls_port": 8445,
                "xhttp_tls_path": "/sg-xhttp-tls",
                "xhttp_tls_mode": "auto",
                "hysteria2_enabled": False,
                "hysteria2_port": 8446,
            }
        )
    _save("xray", xray_host, xray_port, xray_config)

    awg = get_connection_settings("amneziawg")
    awg_config = dict(awg.config)
    awg_host = str(awg.host or "").strip() or public_host
    requested_awg_port = _port(_text("SG_SEED_AWG_PORT"), AMNEZIAWG_UDP_PORT)
    if requested_awg_port != AMNEZIAWG_UDP_PORT:
        raise RuntimeError(
            f"SG-Gateway requires AmneziaWG UDP {AMNEZIAWG_UDP_PORT}; "
            f"installer requested {requested_awg_port}"
        )
    awg_port = AMNEZIAWG_UDP_PORT
    _country(awg_config, country)
    awg_config.setdefault("allowed_ips", "0.0.0.0/0, ::/0")
    awg_config.setdefault("persistent_keepalive", 25)
    if not _usable(awg_config.get("server_public_key")):
        awg_config["server_public_key"] = awg_public_key
    if not update_mode:
        awg_config.update(
            {
                "server_public_key": awg_public_key,
                "allowed_ips": "0.0.0.0/0, ::/0",
                "persistent_keepalive": 25,
            }
        )
    _save("amneziawg", awg_host, awg_port, awg_config)

    awg3 = get_connection_settings("amneziawg3")
    awg3_config = dict(awg3.config)
    awg3_host = str(awg3.host or "").strip() or awg_host or public_host
    _country(awg3_config, country)
    awg3_config.setdefault("allowed_ips", "0.0.0.0/0, ::/0")
    awg3_config.setdefault("persistent_keepalive", "25-35")
    awg3_config["generation"] = 3
    _save("amneziawg3", awg3_host, AMNEZIAWG3_UDP_PORT, awg3_config)

    mihomo = get_connection_settings("mihomo")
    mihomo_config = dict(mihomo.config)
    mihomo_host = str(mihomo.host or "").strip() or public_host
    mihomo_port = _port(mihomo.port, 2099)
    _country(mihomo_config, country)
    if not update_mode:
        mihomo_config.update(
            {
                "mieru_enabled": True,
                "mieru_port": 2099,
                "anytls_enabled": False,
                "anytls_port": 9443,
                "tuic_enabled": False,
                "tuic_port": 10443,
            }
        )
    _save("mihomo", mihomo_host, mihomo_port, mihomo_config)

    synchronized_credentials = _synchronize_xray_credentials(
        host=xray_host,
        port=xray_port,
        fingerprint=str(xray_config.get("fingerprint") or "firefox"),
        server_name=str(xray_config.get("server_name") or "bing.com"),
        public_key=xray_public_key,
        short_id=xray_short_id,
        vless_encryption=vless_encryption,
    )

    created_admin = False
    if (
        _text("SG_SEED_CREATE_ADMIN", "1") == "1"
        and count_clients() == 0
    ):
        admin_client_id = create_client(
            "sg-admin",
            "xray_reality_tcp,xray_xhttp_reality,amneziawg,mihomo,sgclient",
        )
        if not admin_client_id:
            raise RuntimeError("Не удалось создать первого клиента sg-admin")
        created_admin = True

    mode = "migration" if update_mode else "seed"
    print(
        "Database "
        f"{mode}: OK; host={public_host}; country={country}; "
        f"xray_credentials_synchronized={synchronized_credentials}; "
        f"sg_admin_created={int(created_admin)}"
    )


if __name__ == "__main__":
    seed_or_migrate()
