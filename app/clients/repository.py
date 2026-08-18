from __future__ import annotations

import hmac
import json
from dataclasses import dataclass

from app.db import connect, init_db
from app.engines.provisioning import build_engine_config
from app.maintenance.operations import log_operation
from app.security.tls import overview as tls_overview


MAX_CLIENT_NAME_LENGTH = 80
MAX_DEVICE_NAME_LENGTH = 60
PRIMARY_DEVICE_NAME = "Основной доступ"
SUPPORTED_ENGINES = (
    "amneziawg",
    "amneziawg3",
    "xray",
    "mihomo",
    "anytls",
    "tuic",
    "sgclient",
)
RUNTIME_ENGINES = ("amneziawg", "amneziawg3", "xray", "mihomo", "anytls", "tuic")
XRAY_PROFILE_TOKENS = {
    "xray_reality_tcp": "reality_tcp",
    "xray_xhttp_reality": "xhttp_reality",
    "xray_xhttp_tls": "xhttp_tls",
    "xray_hysteria2": "hysteria2",
}
DEFAULT_XRAY_PROFILES = ("reality_tcp", "xhttp_reality")
TLS_PROTOCOL_TOKENS = {"xray_xhttp_tls", "xray_hysteria2", "anytls", "tuic"}


@dataclass(frozen=True)
class Client:
    id: int
    name: str
    enabled: bool
    expires_at: str | None
    awg_status: str
    xray_status: str
    mihomo_status: str = "missing"
    anytls_status: str = "missing"
    tuic_status: str = "missing"
    sgclient_status: str = "missing"
    device_count: int = 0
    active_device_count: int = 0
    awg3_status: str = "missing"


@dataclass(frozen=True)
class Device:
    id: int
    client_id: int
    name: str
    enabled: bool
    expires_at: str | None
    is_primary: bool
    created_at: str
    last_seen_at: str | None = None


@dataclass(frozen=True)
class ClientDeployment:
    """Compatibility name for one device credential.

    Preview 45 called these rows client deployments.  Keeping the public class
    name prevents older tests/extensions from breaking while the storage model
    is now device_credentials.
    """

    engine: str
    status: str
    engine_object_id: str | None
    config_json: str | None
    device_id: int = 0


@dataclass(frozen=True)
class CredentialSnapshot:
    id: int
    engine: str
    status: str
    engine_object_id: str | None
    config_json: str | None
    rotated_at: str | None
    created_at: str


@dataclass(frozen=True)
class DeviceSnapshot:
    id: int
    name: str
    enabled: bool
    expires_at: str | None
    is_primary: bool
    last_seen_at: str | None
    created_at: str
    credentials: tuple[CredentialSnapshot, ...]


@dataclass(frozen=True)
class ClientSnapshot:
    id: int
    name: str
    enabled: bool
    expires_at: str | None
    created_at: str
    devices: tuple[DeviceSnapshot, ...]

    @property
    def deployments(self) -> tuple[CredentialSnapshot, ...]:
        """Legacy view: credentials of the primary device."""
        primary = next((item for item in self.devices if item.is_primary), None)
        return primary.credentials if primary else ()


_STATUS_PRIORITY = {
    "error": 90,
    "applying": 80,
    "checking": 75,
    "creating": 70,
    "pending": 60,
    "generated": 60,
    "applied": 50,
    "disabled": 20,
    "missing": 0,
}


def _aggregate_status(rows, engine: str) -> str:
    values = [str(row["status"]) for row in rows if str(row["engine"]) == engine]
    if not values:
        return "missing"
    return max(values, key=lambda value: _STATUS_PRIORITY.get(value, 10))


def _row_to_device(row) -> Device:
    return Device(
        id=int(row["id"]),
        client_id=int(row["client_id"]),
        name=str(row["name"]),
        enabled=bool(row["enabled"]),
        expires_at=row["expires_at"],
        is_primary=bool(row["is_primary"]),
        created_at=str(row["created_at"]),
        last_seen_at=row["last_seen_at"],
    )


def _clean_name(value: str, maximum: int) -> str | None:
    clean = " ".join((value or "").split())
    if not clean or len(clean) > maximum:
        return None
    return clean


def _clean_client_name(name: str) -> str | None:
    return _clean_name(name, MAX_CLIENT_NAME_LENGTH)


def _clean_device_name(name: str) -> str | None:
    return _clean_name(name, MAX_DEVICE_NAME_LENGTH)


def _client_name_exists(connection, clean_name: str) -> bool:
    rows = connection.execute("SELECT name FROM clients").fetchall()
    wanted = clean_name.casefold()
    return any(str(row["name"]).casefold() == wanted for row in rows)


def _device_name_exists(connection, client_id: int, clean_name: str) -> bool:
    rows = connection.execute(
        "SELECT name FROM devices WHERE client_id = ?", (client_id,)
    ).fetchall()
    wanted = clean_name.casefold()
    return any(str(row["name"]).casefold() == wanted for row in rows)


def _parse_access(access: str) -> tuple[list[str], list[str], list[str]]:
    value = (access or "").strip().lower()
    aliases = {
        "recommended": "xray_xhttp_reality,sgclient",
        "full": (
            "amneziawg,amneziawg3,xray_reality_tcp,xray_xhttp_reality,"
            "xray_xhttp_tls,xray_hysteria2,sgclient"
        ),
        "xray": "xray_reality_tcp,xray_xhttp_reality",
    }
    value = aliases.get(value, value)
    raw_tokens: list[str] = []
    for item in value.split(","):
        token = item.strip()
        if token and token not in raw_tokens:
            raw_tokens.append(token)

    engines: list[str] = []
    xray_profiles: list[str] = []
    for token in raw_tokens:
        profile = XRAY_PROFILE_TOKENS.get(token)
        if profile:
            if profile not in xray_profiles:
                xray_profiles.append(profile)
            if "xray" not in engines:
                engines.append("xray")
            continue
        if token == "xray":
            for profile_id in DEFAULT_XRAY_PROFILES:
                if profile_id not in xray_profiles:
                    xray_profiles.append(profile_id)
            if "xray" not in engines:
                engines.append("xray")
            continue
        if token in SUPPORTED_ENGINES and token not in engines:
            engines.append(token)
    return engines, xray_profiles, raw_tokens


def _validate_access(engines: list[str], raw_tokens: list[str]) -> str | None:
    if not engines:
        return "Не выбран ни один протокол"
    if TLS_PROTOCOL_TOKENS & set(raw_tokens):
        if not bool(tls_overview().get("https_ready")):
            return "TLS-протоколы требуют настроенного HTTPS в Security"
    sources = {"xray", "mihomo", "anytls", "tuic"}
    if "sgclient" in engines and not (sources & set(engines)):
        return "SG Client требует хотя бы один ссылочный протокол"
    return None


def _create_device_rows(
    connection,
    *,
    client_id: int,
    client_name: str,
    device_name: str,
    access: str,
    expires_at: str | None,
    is_primary: bool,
) -> int:
    engines, xray_profiles, raw_tokens = _parse_access(access)
    error = _validate_access(engines, raw_tokens)
    if error:
        raise ValueError(error)

    cursor = connection.execute(
        """
        INSERT INTO devices (client_id, name, enabled, expires_at, is_primary)
        VALUES (?, ?, 1, ?, ?)
        """,
        (client_id, device_name, expires_at or None, 1 if is_primary else 0),
    )
    device_id = int(cursor.lastrowid)
    access_label = client_name if is_primary else f"{client_name} · {device_name}"

    for engine in engines:
        object_id, config_json = build_engine_config(engine, device_id, access_label)
        if engine == "xray":
            payload = json.loads(config_json)
            payload["profiles"] = xray_profiles or list(DEFAULT_XRAY_PROFILES)
            payload["device_id"] = device_id
            payload["client_id"] = client_id
            config_json = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        connection.execute(
            """
            INSERT INTO device_credentials (
                device_id, engine, status, engine_object_id, config_json
            )
            VALUES (?, ?, 'creating', ?, ?)
            """,
            (device_id, engine, object_id, config_json),
        )
    return device_id


def _client_from_row(connection, row) -> Client:
    client_id = int(row["id"])
    devices = connection.execute(
        "SELECT id, enabled FROM devices WHERE client_id = ?", (client_id,)
    ).fetchall()
    credentials = connection.execute(
        """
        SELECT dc.engine, dc.status
        FROM device_credentials dc
        JOIN devices d ON d.id = dc.device_id
        WHERE d.client_id = ?
        """,
        (client_id,),
    ).fetchall()
    return Client(
        id=client_id,
        name=str(row["name"]),
        enabled=bool(row["enabled"]),
        expires_at=row["expires_at"],
        awg_status=_aggregate_status(credentials, "amneziawg"),
        awg3_status=_aggregate_status(credentials, "amneziawg3"),
        xray_status=_aggregate_status(credentials, "xray"),
        mihomo_status=_aggregate_status(credentials, "mihomo"),
        anytls_status=_aggregate_status(credentials, "anytls"),
        tuic_status=_aggregate_status(credentials, "tuic"),
        sgclient_status=_aggregate_status(credentials, "sgclient"),
        device_count=len(devices),
        active_device_count=sum(1 for item in devices if bool(item["enabled"])),
    )


def list_clients() -> list[Client]:
    init_db()
    with connect() as connection:
        rows = connection.execute(
            "SELECT id, name, enabled, expires_at FROM clients ORDER BY id DESC"
        ).fetchall()
        return [_client_from_row(connection, row) for row in rows]


def get_client(client_id: int) -> Client | None:
    init_db()
    with connect() as connection:
        row = connection.execute(
            "SELECT id, name, enabled, expires_at FROM clients WHERE id = ?",
            (client_id,),
        ).fetchone()
        return _client_from_row(connection, row) if row else None


def list_devices(client_id: int) -> list[Device]:
    init_db()
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT id, client_id, name, enabled, expires_at, is_primary,
                   created_at, last_seen_at
            FROM devices
            WHERE client_id = ?
            ORDER BY is_primary DESC, id
            """,
            (client_id,),
        ).fetchall()
    return [_row_to_device(row) for row in rows]


def get_device(device_id: int, client_id: int | None = None) -> Device | None:
    init_db()
    query = """
        SELECT id, client_id, name, enabled, expires_at, is_primary,
               created_at, last_seen_at
        FROM devices WHERE id = ?
    """
    params: tuple = (device_id,)
    if client_id is not None:
        query += " AND client_id = ?"
        params = (device_id, client_id)
    with connect() as connection:
        row = connection.execute(query, params).fetchone()
    return _row_to_device(row) if row else None


def get_primary_device(client_id: int) -> Device | None:
    init_db()
    with connect() as connection:
        row = connection.execute(
            """
            SELECT id, client_id, name, enabled, expires_at, is_primary,
                   created_at, last_seen_at
            FROM devices
            WHERE client_id = ?
            ORDER BY is_primary DESC, id
            LIMIT 1
            """,
            (client_id,),
        ).fetchone()
    return _row_to_device(row) if row else None


def list_device_credentials(device_id: int) -> list[ClientDeployment]:
    init_db()
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT engine, status, engine_object_id, config_json
            FROM device_credentials
            WHERE device_id = ?
            ORDER BY engine
            """,
            (device_id,),
        ).fetchall()
    return [
        ClientDeployment(
            engine=str(row["engine"]),
            status=str(row["status"]),
            engine_object_id=row["engine_object_id"],
            config_json=row["config_json"],
            device_id=device_id,
        )
        for row in rows
    ]


def list_client_deployments(client_id: int) -> list[ClientDeployment]:
    """Legacy wrapper returning credentials of the primary access."""
    device = get_primary_device(client_id)
    return list_device_credentials(device.id) if device else []


def count_clients() -> int:
    init_db()
    with connect() as connection:
        row = connection.execute("SELECT COUNT(*) AS total FROM clients").fetchone()
    return int(row["total"])


def count_devices() -> int:
    init_db()
    with connect() as connection:
        row = connection.execute("SELECT COUNT(*) AS total FROM devices").fetchone()
    return int(row["total"])


def create_client(name: str, access: str, expires_at: str | None = None) -> int | None:
    init_db()
    clean_name = _clean_client_name(name)
    if clean_name is None:
        log_operation("client.create", "client:new", "Отклонено недопустимое имя клиента", status="error")
        return None

    engines, _, raw_tokens = _parse_access(access)
    error = _validate_access(engines, raw_tokens)
    if error:
        log_operation("client.create", "client:new", error, status="error")
        return None

    with connect() as connection:
        if _client_name_exists(connection, clean_name):
            log_operation("client.create", "client:new", f"Отклонено повторяющееся имя клиента: {clean_name}", status="error")
            return None
        cursor = connection.execute(
            "INSERT INTO clients (name, enabled, expires_at) VALUES (?, 1, ?)",
            (clean_name, expires_at or None),
        )
        client_id = int(cursor.lastrowid)
        try:
            _create_device_rows(
                connection,
                client_id=client_id,
                client_name=clean_name,
                device_name=PRIMARY_DEVICE_NAME,
                access=access,
                expires_at=expires_at,
                is_primary=True,
            )
        except Exception:
            connection.execute("DELETE FROM clients WHERE id = ?", (client_id,))
            raise

    log_operation(
        "client.create",
        f"client:{client_id}",
        f"Создан клиент {clean_name} с основным доступом",
    )
    return client_id


def create_device(
    client_id: int,
    name: str,
    access: str,
    expires_at: str | None = None,
) -> int | None:
    init_db()
    clean_name = _clean_device_name(name)
    if clean_name is None or clean_name.casefold() == PRIMARY_DEVICE_NAME.casefold():
        return None
    engines, _, raw_tokens = _parse_access(access)
    if _validate_access(engines, raw_tokens):
        return None
    with connect() as connection:
        client = connection.execute(
            "SELECT id, name, enabled FROM clients WHERE id = ?", (client_id,)
        ).fetchone()
        if client is None or _device_name_exists(connection, client_id, clean_name):
            return None
        device_id = _create_device_rows(
            connection,
            client_id=client_id,
            client_name=str(client["name"]),
            device_name=clean_name,
            access=access,
            expires_at=expires_at,
            is_primary=False,
        )
    log_operation(
        "device.create",
        f"device:{device_id}",
        f"Для клиента {client_id} создан отдельный доступ «{clean_name}»",
    )
    return device_id



def device_access_tokens(device_id: int) -> list[str]:
    """Return the exact form tokens currently assigned to one device."""
    result: list[str] = []
    reverse_profiles = {value: key for key, value in XRAY_PROFILE_TOKENS.items()}
    for credential in list_device_credentials(device_id):
        if credential.engine == "xray":
            try:
                payload = json.loads(credential.config_json or "{}")
            except (TypeError, ValueError, json.JSONDecodeError):
                payload = {}
            profiles = payload.get("profiles") if isinstance(payload, dict) else None
            if not isinstance(profiles, list):
                profiles = list(DEFAULT_XRAY_PROFILES)
            for profile in profiles:
                token = reverse_profiles.get(str(profile))
                if token and token not in result:
                    result.append(token)
            continue
        if credential.engine in SUPPORTED_ENGINES and credential.engine not in result:
            result.append(credential.engine)
    return result


def _client_name_exists_except(connection, clean_name: str, client_id: int) -> bool:
    rows = connection.execute(
        "SELECT id, name FROM clients WHERE id != ?", (client_id,)
    ).fetchall()
    wanted = clean_name.casefold()
    return any(str(row["name"]).casefold() == wanted for row in rows)


def _device_name_exists_except(
    connection,
    client_id: int,
    clean_name: str,
    device_id: int,
) -> bool:
    rows = connection.execute(
        "SELECT id, name FROM devices WHERE client_id = ? AND id != ?",
        (client_id, device_id),
    ).fetchall()
    wanted = clean_name.casefold()
    return any(str(row["name"]).casefold() == wanted for row in rows)


def _credential_label_payload(
    raw: str | None,
    *,
    label: str,
    engine: str,
    client_id: int,
    device_id: int,
    xray_profiles: list[str] | None = None,
) -> str | None:
    try:
        payload = json.loads(raw or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        return raw
    if not isinstance(payload, dict):
        return raw
    payload["client_name"] = label
    if engine == "xray":
        if xray_profiles is not None:
            payload["profiles"] = xray_profiles or list(DEFAULT_XRAY_PROFILES)
        payload["client_id"] = client_id
        payload["device_id"] = device_id
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _sync_device_access(
    connection,
    *,
    client_id: int,
    device_id: int,
    client_name: str,
    device_name: str,
    is_primary: bool,
    access: str,
) -> None:
    engines, xray_profiles, raw_tokens = _parse_access(access)
    error = _validate_access(engines, raw_tokens)
    if error:
        raise ValueError(error)

    rows = connection.execute(
        """
        SELECT id, engine, status, engine_object_id, config_json
        FROM device_credentials
        WHERE device_id = ?
        ORDER BY id
        """,
        (device_id,),
    ).fetchall()
    existing = {str(row["engine"]): row for row in rows}
    wanted = set(engines)

    for engine, row in existing.items():
        if engine not in wanted:
            connection.execute(
                "DELETE FROM device_credentials WHERE id = ?", (int(row["id"]),)
            )

    label = client_name if is_primary else f"{client_name} · {device_name}"
    for engine in engines:
        row = existing.get(engine)
        if row is not None:
            config_json = _credential_label_payload(
                row["config_json"],
                label=label,
                engine=engine,
                client_id=client_id,
                device_id=device_id,
                xray_profiles=xray_profiles if engine == "xray" else None,
            )
            connection.execute(
                "UPDATE device_credentials SET config_json = ? WHERE id = ?",
                (config_json, int(row["id"])),
            )
            continue

        object_id, config_json = build_engine_config(engine, device_id, label)
        if engine == "xray":
            payload = json.loads(config_json)
            payload["profiles"] = xray_profiles or list(DEFAULT_XRAY_PROFILES)
            payload["device_id"] = device_id
            payload["client_id"] = client_id
            config_json = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        connection.execute(
            """
            INSERT INTO device_credentials (
                device_id, engine, status, engine_object_id, config_json
            ) VALUES (?, ?, 'creating', ?, ?)
            """,
            (device_id, engine, object_id, config_json),
        )


def _refresh_client_labels(connection, client_id: int, client_name: str) -> None:
    devices = connection.execute(
        "SELECT id, name, is_primary FROM devices WHERE client_id = ? ORDER BY id",
        (client_id,),
    ).fetchall()
    for device in devices:
        device_id = int(device["id"])
        label = (
            client_name
            if bool(device["is_primary"])
            else f"{client_name} · {str(device['name'])}"
        )
        credentials = connection.execute(
            "SELECT id, engine, config_json FROM device_credentials WHERE device_id = ?",
            (device_id,),
        ).fetchall()
        for credential in credentials:
            config_json = _credential_label_payload(
                credential["config_json"],
                label=label,
                engine=str(credential["engine"]),
                client_id=client_id,
                device_id=device_id,
            )
            connection.execute(
                "UPDATE device_credentials SET config_json = ? WHERE id = ?",
                (config_json, int(credential["id"])),
            )


def update_client(
    client_id: int,
    name: str,
    expires_at: str | None,
    access: str,
) -> bool:
    """Edit a client and its primary access without rotating unchanged secrets."""
    init_db()
    clean_name = _clean_client_name(name)
    if clean_name is None:
        raise ValueError("Недопустимое имя клиента")

    with connect() as connection:
        client = connection.execute(
            "SELECT id, name FROM clients WHERE id = ?", (client_id,)
        ).fetchone()
        if client is None:
            return False
        if _client_name_exists_except(connection, clean_name, client_id):
            raise ValueError("Клиент с таким именем уже существует")
        primary = connection.execute(
            """
            SELECT id, name, is_primary
            FROM devices
            WHERE client_id = ?
            ORDER BY is_primary DESC, id
            LIMIT 1
            """,
            (client_id,),
        ).fetchone()
        if primary is None:
            raise ValueError("У клиента отсутствует основной доступ")

        primary_id = int(primary["id"])
        connection.execute(
            "UPDATE clients SET name = ?, expires_at = ? WHERE id = ?",
            (clean_name, expires_at or None, client_id),
        )
        connection.execute(
            "UPDATE devices SET expires_at = ? WHERE id = ?",
            (expires_at or None, primary_id),
        )
        _sync_device_access(
            connection,
            client_id=client_id,
            device_id=primary_id,
            client_name=clean_name,
            device_name=str(primary["name"]),
            is_primary=True,
            access=access,
        )
        _refresh_client_labels(connection, client_id, clean_name)

    log_operation(
        "client.update",
        f"client:{client_id}",
        f"Клиент обновлён: {clean_name}; неизменённые реквизиты сохранены",
    )
    return True


def update_device(
    client_id: int,
    device_id: int,
    name: str,
    expires_at: str | None,
    access: str,
) -> bool:
    """Edit one additional device while preserving unchanged credentials."""
    init_db()
    clean_name = _clean_device_name(name)
    if clean_name is None or clean_name.casefold() == PRIMARY_DEVICE_NAME.casefold():
        raise ValueError("Недопустимое имя устройства")

    with connect() as connection:
        client = connection.execute(
            "SELECT id, name FROM clients WHERE id = ?", (client_id,)
        ).fetchone()
        device = connection.execute(
            """
            SELECT id, name, is_primary
            FROM devices
            WHERE id = ? AND client_id = ?
            """,
            (device_id, client_id),
        ).fetchone()
        if client is None or device is None:
            return False
        if bool(device["is_primary"]):
            raise ValueError("Основной доступ редактируется вместе с клиентом")
        if _device_name_exists_except(connection, client_id, clean_name, device_id):
            raise ValueError("Устройство с таким именем уже существует")

        connection.execute(
            "UPDATE devices SET name = ?, expires_at = ? WHERE id = ?",
            (clean_name, expires_at or None, device_id),
        )
        _sync_device_access(
            connection,
            client_id=client_id,
            device_id=device_id,
            client_name=str(client["name"]),
            device_name=clean_name,
            is_primary=False,
            access=access,
        )

    log_operation(
        "device.update",
        f"device:{device_id}",
        f"Устройство обновлено: {clean_name}; неизменённые реквизиты сохранены",
    )
    return True

def set_client_enabled(client_id: int, enabled: bool) -> bool:
    init_db()
    with connect() as connection:
        cursor = connection.execute(
            "UPDATE clients SET enabled = ? WHERE id = ?",
            (1 if enabled else 0, client_id),
        )
    if cursor.rowcount == 0:
        return False
    log_operation(
        "client.enable" if enabled else "client.disable",
        f"client:{client_id}",
        "Клиент включён" if enabled else "Клиент отключён со всеми доступами",
    )
    return True


def set_device_enabled(device_id: int, enabled: bool) -> bool:
    init_db()
    with connect() as connection:
        cursor = connection.execute(
            "UPDATE devices SET enabled = ? WHERE id = ?",
            (1 if enabled else 0, device_id),
        )
    if cursor.rowcount == 0:
        return False
    log_operation(
        "device.enable" if enabled else "device.disable",
        f"device:{device_id}",
        "Доступ включён" if enabled else "Доступ отключён независимо от остальных",
    )
    return True


def delete_device(device_id: int) -> bool:
    init_db()
    with connect() as connection:
        row = connection.execute(
            "SELECT is_primary FROM devices WHERE id = ?", (device_id,)
        ).fetchone()
        if row is None or bool(row["is_primary"]):
            return False
        cursor = connection.execute("DELETE FROM devices WHERE id = ?", (device_id,))
    if cursor.rowcount:
        log_operation("device.delete", f"device:{device_id}", "Дополнительный доступ удалён")
        return True
    return False


def delete_client(client_id: int) -> bool:
    init_db()
    with connect() as connection:
        cursor = connection.execute("DELETE FROM clients WHERE id = ?", (client_id,))
    if cursor.rowcount == 0:
        return False
    log_operation("client.delete", f"client:{client_id}", "Клиент и все его доступы удалены")
    return True


def snapshot_client(client_id: int) -> ClientSnapshot | None:
    init_db()
    with connect() as connection:
        client = connection.execute(
            "SELECT id, name, enabled, expires_at, created_at FROM clients WHERE id = ?",
            (client_id,),
        ).fetchone()
        if client is None:
            return None
        device_rows = connection.execute(
            """
            SELECT id, name, enabled, expires_at, is_primary,
                   last_seen_at, created_at
            FROM devices WHERE client_id = ? ORDER BY id
            """,
            (client_id,),
        ).fetchall()
        devices: list[DeviceSnapshot] = []
        for device in device_rows:
            creds = connection.execute(
                """
                SELECT id, engine, status, engine_object_id, config_json,
                       rotated_at, created_at
                FROM device_credentials WHERE device_id = ? ORDER BY id
                """,
                (int(device["id"]),),
            ).fetchall()
            devices.append(
                DeviceSnapshot(
                    id=int(device["id"]),
                    name=str(device["name"]),
                    enabled=bool(device["enabled"]),
                    expires_at=device["expires_at"],
                    is_primary=bool(device["is_primary"]),
                    last_seen_at=device["last_seen_at"],
                    created_at=str(device["created_at"]),
                    credentials=tuple(
                        CredentialSnapshot(
                            id=int(item["id"]),
                            engine=str(item["engine"]),
                            status=str(item["status"]),
                            engine_object_id=item["engine_object_id"],
                            config_json=item["config_json"],
                            rotated_at=item["rotated_at"],
                            created_at=str(item["created_at"]),
                        )
                        for item in creds
                    ),
                )
            )
    return ClientSnapshot(
        id=int(client["id"]),
        name=str(client["name"]),
        enabled=bool(client["enabled"]),
        expires_at=client["expires_at"],
        created_at=str(client["created_at"]),
        devices=tuple(devices),
    )


def restore_client_snapshot(snapshot: ClientSnapshot) -> bool:
    init_db()
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO clients (id, name, enabled, expires_at, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              name=excluded.name, enabled=excluded.enabled,
              expires_at=excluded.expires_at, created_at=excluded.created_at
            """,
            (
                snapshot.id,
                snapshot.name,
                1 if snapshot.enabled else 0,
                snapshot.expires_at,
                snapshot.created_at,
            ),
        )
        connection.execute("DELETE FROM devices WHERE client_id = ?", (snapshot.id,))
        for device in snapshot.devices:
            connection.execute(
                """
                INSERT INTO devices (
                    id, client_id, name, enabled, expires_at, is_primary,
                    last_seen_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    device.id,
                    snapshot.id,
                    device.name,
                    1 if device.enabled else 0,
                    device.expires_at,
                    1 if device.is_primary else 0,
                    device.last_seen_at,
                    device.created_at,
                ),
            )
            for credential in device.credentials:
                connection.execute(
                    """
                    INSERT INTO device_credentials (
                        id, device_id, engine, status, engine_object_id,
                        config_json, rotated_at, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        credential.id,
                        device.id,
                        credential.engine,
                        credential.status,
                        credential.engine_object_id,
                        credential.config_json,
                        credential.rotated_at,
                        credential.created_at,
                    ),
                )
    log_operation("client.rollback", f"client:{snapshot.id}", "Клиент и его доступы восстановлены после ошибки runtime")
    return True


def get_subscription_access(token: str) -> tuple[Client, Device] | None:
    clean = str(token or "").strip()
    if len(clean) < 24 or len(clean) > 256:
        return None

    init_db()
    found = None
    with connect() as connection:
        rows = connection.execute(
            "SELECT dc.config_json, d.id AS device_id, d.client_id AS client_id "
            "FROM device_credentials dc "
            "JOIN devices d ON d.id = dc.device_id "
            "WHERE dc.engine = 'sgclient' ORDER BY dc.id"
        ).fetchall()
        for row in rows:
            try:
                config = json.loads(row["config_json"] or "{}")
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            if not isinstance(config, dict):
                continue
            stored = str(config.get("subscription_token") or "").strip()
            if stored and hmac.compare_digest(stored, clean):
                found = (int(row["client_id"]), int(row["device_id"]))
                break

    if found is None:
        return None
    client = get_client(found[0])
    device = get_device(found[1], found[0])
    if client is None or device is None:
        return None
    return client, device
