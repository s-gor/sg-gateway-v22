from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass

from app.db import connect, init_db

ENGINE_ID = "amneziawg31"
PROFILE_ID = "awg31"
HOST = "awg31.internal"
PORT = 587
ENDPOINT = f"{HOST}:{PORT}"
TRANSPORT = "udp"
DNS = "1.1.1.1"
AWG31_MTU = 1420
AWG31_PROTOCOL_OVERHEAD = 128
MAX_I_PAYLOAD_SIZE = AWG31_MTU - AWG31_PROTOCOL_OVERHEAD
I_TIMESTAMP_SIZE = 8
_I_TAG_RE = re.compile(
    r"(?:<b 0x(?P<hex>[0-9A-Fa-f]+)>|<(?P<size_tag>rd|rc|r) (?P<size>\d+)>|(?P<time><t>))"
)

I_FIELDS = tuple(f"I{index}" for index in range(1, 6))
J_FIELDS = ("Jc", "Jmin", "Jmax")
S_FIELDS = tuple(f"S{index}" for index in range(1, 5))
H_FIELDS = tuple(f"H{index}" for index in range(1, 5))
RANGE_FIELDS = (
    "ContentPaddingAddition",
    "RekeyAfterTime",
    "RekeyTimeout",
    "RejectAfterTime",
    "KeepaliveTimeout",
    "MaxHandshakeAttempts",
)
BOOL_FIELDS = ("RandomTrailers", "DisableCookies")
FIELD_NAMES = I_FIELDS + J_FIELDS + S_FIELDS + H_FIELDS + RANGE_FIELDS + BOOL_FIELDS

REAL31_DEFAULT_PARAMETERS: dict[str, str | int] = {
    **{name: "" for name in I_FIELDS},
    "Jc": 4,
    "Jmin": 10,
    "Jmax": 50,
    "S1": 64,
    "S2": 96,
    "S3": 48,
    "S4": 12,
    "H1": "1085466381",
    "H2": "1525636359",
    "H3": "1894947610",
    "H4": "2767261704",
    "ContentPaddingAddition": "10-100",
    "RekeyAfterTime": "100-120",
    "RekeyTimeout": "3-7",
    "RejectAfterTime": "150-180",
    "KeepaliveTimeout": "5-15",
    "MaxHandshakeAttempts": "15-20",
    "RandomTrailers": "on",
    "DisableCookies": "on",
}
DEFAULT_PARAMETERS = dict(REAL31_DEFAULT_PARAMETERS)


class Awg31ValidationError(ValueError):
    pass


@dataclass(frozen=True)
class Awg31Settings:
    parameters: dict[str, str | int]
    server_public_key: str = ""
    header_protection_key: str = ""
    enabled: bool = True
    host: str = HOST
    port: int = PORT
    dns: str = DNS
    transport: str = TRANSPORT

    @property
    def advanced_security(self) -> bool:
        return bool(self.header_protection_key)

    def as_api(self) -> dict:
        return {
            "profile": PROFILE_ID,
            "engine": ENGINE_ID,
            "enabled": self.enabled,
            "host": self.host,
            "port": self.port,
            "endpoint": ENDPOINT,
            "transport": self.transport,
            "dns": self.dns,
            "service": "sg-gateway-awg31.service",
            "advanced_security": self.advanced_security,
            "parameters": dict(self.parameters),
        }


def _uint16(name: str, value: object) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise Awg31ValidationError(f"{name} must be an integer") from exc
    if parsed < 0 or parsed > 65535:
        raise Awg31ValidationError(f"{name} must be between 0 and 65535")
    return parsed


def _range_parts(name: str, value: object, maximum: int) -> tuple[str, int, int]:
    text = str(value).strip()
    match = re.fullmatch(r"(\d+)(?:-(\d+))?", text)
    if not match:
        raise Awg31ValidationError(f"{name} must be an unsigned integer or range")
    low = int(match.group(1))
    high = int(match.group(2) or low)
    if low > maximum or high > maximum or high < low:
        raise Awg31ValidationError(f"{name} range is invalid")
    normalized = str(low) if low == high else f"{low}-{high}"
    return normalized, low, high


def _bool_value(name: str, value: object) -> str:
    normalized = str(value).strip().lower()
    if normalized in {"on", "1", "true", "yes"}:
        return "on"
    if normalized in {"off", "0", "false", "no"}:
        return "off"
    raise Awg31ValidationError(f"{name} must be on or off")


def _legacy_stage3a(values: Mapping[str, object]) -> bool:
    headers = [str(values.get(name, "")).strip() for name in H_FIELDS]
    return (
        all(str(values.get(name, "0")).strip() == "0" for name in J_FIELDS + S_FIELDS)
        and headers in (["0", "0", "0", "0"], ["1", "2", "3", "4"])
    )


def normalize_legacy_parameters(values: Mapping[str, object]) -> dict[str, object]:
    normalized = dict(values)
    if _legacy_stage3a(normalized):
        normalized.update(REAL31_DEFAULT_PARAMETERS)
    for name, default in REAL31_DEFAULT_PARAMETERS.items():
        if name not in normalized or normalized[name] is None or str(normalized[name]).strip() == "":
            if name not in I_FIELDS:
                normalized[name] = default
    return normalized


def _tagged_junk(name: str, value: object) -> tuple[str, int]:
    text = str(value)
    if not text.strip():
        return "", 0
    if text != text.strip():
        raise Awg31ValidationError(f"{name} must contain tags only")
    if any(char in text for char in ("\r", "\n", "\x00")):
        raise Awg31ValidationError(f"{name} contains forbidden control characters")

    position = 0
    payload_size = 0
    while position < len(text):
        match = _I_TAG_RE.match(text, position)
        if match is None:
            raise Awg31ValidationError(
                f"{name} must be a sequence of <b 0xHEX>, <r N>, <rd N>, <rc N>, or <t> tags"
            )
        if match.group("hex") is not None:
            hex_value = match.group("hex")
            if len(hex_value) % 2:
                raise Awg31ValidationError(f"{name} hex payload must contain whole bytes")
            payload_size += len(hex_value) // 2
        elif match.group("size") is not None:
            size = int(match.group("size"))
            if size > MAX_I_PAYLOAD_SIZE:
                raise Awg31ValidationError(f"{name} tag size exceeds the AWG31 MTU-safe limit")
            payload_size += size
        else:
            payload_size += I_TIMESTAMP_SIZE
        if payload_size > MAX_I_PAYLOAD_SIZE:
            raise Awg31ValidationError(f"{name} expanded payload exceeds the AWG31 MTU-safe limit")
        position = match.end()
    return text, payload_size


def validate_parameters(values: Mapping[str, object]) -> dict[str, str | int]:
    values = normalize_legacy_parameters(values)
    unknown = set(values) - set(FIELD_NAMES)
    if unknown:
        raise Awg31ValidationError("Unknown AWG31 fields: " + ", ".join(sorted(unknown)))

    result: dict[str, str | int] = {}
    total_i_payload = 0
    for name in I_FIELDS:
        tagged, payload_size = _tagged_junk(name, values.get(name, DEFAULT_PARAMETERS[name]))
        result[name] = tagged
        total_i_payload += payload_size
    if total_i_payload > MAX_I_PAYLOAD_SIZE:
        raise Awg31ValidationError("Combined I1-I5 payload exceeds the AWG31 MTU-safe limit")

    for name in J_FIELDS + S_FIELDS:
        result[name] = _uint16(name, values.get(name, DEFAULT_PARAMETERS[name]))
    if int(result["Jmin"]) > int(result["Jmax"]):
        raise Awg31ValidationError("Jmin must not exceed Jmax")
    if any(int(result[name]) < 12 for name in S_FIELDS):
        raise Awg31ValidationError("S1-S4 must be at least 12 when HeaderProtectionKey is enabled")

    header_ranges: dict[str, tuple[int, int]] = {}
    for name in H_FIELDS:
        normalized, low, high = _range_parts(name, values.get(name, DEFAULT_PARAMETERS[name]), 0xFFFFFFFF)
        result[name] = normalized
        header_ranges[name] = (low, high)
    for index, left_name in enumerate(H_FIELDS):
        left_low, left_high = header_ranges[left_name]
        for right_name in H_FIELDS[index + 1 :]:
            right_low, right_high = header_ranges[right_name]
            if max(left_low, right_low) <= min(left_high, right_high):
                raise Awg31ValidationError(f"{left_name} and {right_name} header ranges must not overlap")

    for name in RANGE_FIELDS:
        normalized, _, _ = _range_parts(name, values.get(name, DEFAULT_PARAMETERS[name]), 65535)
        result[name] = normalized
    for name in BOOL_FIELDS:
        result[name] = _bool_value(name, values.get(name, DEFAULT_PARAMETERS[name]))
    return result


def _storage_config(
    parameters: Mapping[str, str | int],
    server_public_key: str = "",
    header_protection_key: str = "",
    dns: str = DNS,
) -> dict:
    return {
        "profile": PROFILE_ID,
        "generation": 31,
        "dns": dns,
        "transport": TRANSPORT,
        "endpoint": ENDPOINT,
        "allowed_ips": "0.0.0.0/0",
        "server_public_key": server_public_key,
        "header_protection_key": header_protection_key,
        **{name.lower(): value for name, value in parameters.items()},
    }


def _ensure_row() -> None:
    init_db()
    with connect() as connection:
        connection.execute(
            """
            INSERT OR IGNORE INTO connection_settings
                (engine, enabled, host, port, config_json)
            VALUES (?, 1, ?, ?, ?)
            """,
            (
                ENGINE_ID,
                HOST,
                PORT,
                json.dumps(_storage_config(DEFAULT_PARAMETERS), sort_keys=True),
            ),
        )


def get_settings() -> Awg31Settings:
    _ensure_row()
    with connect() as connection:
        row = connection.execute(
            "SELECT enabled, host, port, config_json FROM connection_settings WHERE engine = ?",
            (ENGINE_ID,),
        ).fetchone()
    if row is None:
        raise KeyError(ENGINE_ID)
    try:
        config = json.loads(row["config_json"] or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        config = {}
    raw = {name: config.get(name.lower(), DEFAULT_PARAMETERS[name]) for name in FIELD_NAMES}
    parameters = validate_parameters(raw)
    return Awg31Settings(
        parameters=parameters,
        server_public_key=str(config.get("server_public_key") or ""),
        header_protection_key=str(config.get("header_protection_key") or ""),
        enabled=bool(row["enabled"]),
        host=str(row["host"] or HOST),
        port=int(row["port"] or PORT),
        dns=str(config.get("dns") or DNS),
    )


def _update_storage(
    parameters: Mapping[str, str | int],
    server_public_key: str,
    header_key: str,
    dns: str = DNS,
) -> None:
    config = _storage_config(parameters, server_public_key, header_key, dns)
    with connect() as connection:
        connection.execute(
            """
            UPDATE connection_settings
            SET enabled = 1, host = ?, port = ?, config_json = ?, updated_at = CURRENT_TIMESTAMP
            WHERE engine = ?
            """,
            (HOST, PORT, json.dumps(config, ensure_ascii=False, sort_keys=True), ENGINE_ID),
        )
        rows = connection.execute(
            "SELECT id, config_json FROM device_credentials WHERE engine = ?",
            (ENGINE_ID,),
        ).fetchall()
        for row in rows:
            try:
                peer = json.loads(row["config_json"] or "{}")
            except (TypeError, ValueError, json.JSONDecodeError):
                peer = {}
            if not isinstance(peer, dict):
                peer = {}
            peer.update(config)
            connection.execute(
                "UPDATE device_credentials SET config_json = ?, status = 'pending' WHERE id = ?",
                (json.dumps(peer, ensure_ascii=False, sort_keys=True), int(row["id"])),
            )


def save_settings(values: Mapping[str, object]) -> Awg31Settings:
    current = get_settings()
    merged = dict(current.parameters)
    merged.update(values)
    parameters = validate_parameters(merged)
    _update_storage(
        parameters, current.server_public_key, current.header_protection_key, current.dns
    )
    return get_settings()


def set_server_public_key(value: str) -> None:
    current = get_settings()
    _update_storage(
        current.parameters,
        str(value or "").strip(),
        current.header_protection_key,
        current.dns,
    )


def set_protocol_state(values: Mapping[str, object], header_protection_key: str) -> Awg31Settings:
    current = get_settings()
    parameters = validate_parameters(values)
    key = str(header_protection_key or "").strip()
    if not key:
        raise Awg31ValidationError("HeaderProtectionKey is required for AWG 3.1")
    _update_storage(parameters, current.server_public_key, key, current.dns)
    return get_settings()


def config_lines(settings: Awg31Settings | None = None) -> list[str]:
    current = settings or get_settings()
    lines: list[str] = []
    for name in I_FIELDS + J_FIELDS + S_FIELDS + H_FIELDS:
        value = current.parameters[name]
        if name in I_FIELDS and value == "":
            continue
        lines.append(f"{name} = {value}")
    if current.header_protection_key:
        lines.append(f"HeaderProtectionKey = {current.header_protection_key}")
    for name in RANGE_FIELDS + BOOL_FIELDS:
        lines.append(f"{name} = {current.parameters[name]}")
    return lines
