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
FIELD_NAMES = I_FIELDS + J_FIELDS + S_FIELDS + H_FIELDS
SAFE_HEADER_PARAMETERS: dict[str, str] = {
    "H1": "1",
    "H2": "2",
    "H3": "3",
    "H4": "4",
}
DEFAULT_PARAMETERS: dict[str, str | int] = {
    **{name: "" for name in I_FIELDS},
    "Jc": 0,
    "Jmin": 0,
    "Jmax": 0,
    **{name: 0 for name in S_FIELDS},
    **SAFE_HEADER_PARAMETERS,
}


class Awg31ValidationError(ValueError):
    pass


@dataclass(frozen=True)
class Awg31Settings:
    parameters: dict[str, str | int]
    server_public_key: str = ""
    enabled: bool = True
    host: str = HOST
    port: int = PORT
    dns: str = DNS
    transport: str = TRANSPORT

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


def _u32_range_parts(name: str, value: object) -> tuple[str, int, int]:
    text = str(value).strip()
    match = re.fullmatch(r"(\d+)(?:-(\d+))?", text)
    if not match:
        raise Awg31ValidationError(f"{name} must be an unsigned integer or range")
    low = int(match.group(1))
    high = int(match.group(2) or low)
    if low > 0xFFFFFFFF or high > 0xFFFFFFFF or high < low:
        raise Awg31ValidationError(f"{name} range is invalid")
    normalized = str(low) if low == high else f"{low}-{high}"
    return normalized, low, high


def _u32_range(name: str, value: object) -> str:
    normalized, _, _ = _u32_range_parts(name, value)
    return normalized


def normalize_legacy_parameters(values: Mapping[str, object]) -> dict[str, object]:
    """Repair only the invalid Stage3A all-zero header defaults.

    Arbitrary overlapping user values remain untouched so validation can reject
    them rather than silently changing an explicitly configured profile.
    """

    normalized = dict(values)
    if all(str(normalized.get(name, "")).strip() == "0" for name in H_FIELDS):
        normalized.update(SAFE_HEADER_PARAMETERS)
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
                raise Awg31ValidationError(
                    f"{name} tag size exceeds the AWG31 MTU-safe limit"
                )
            payload_size += size
        else:
            payload_size += I_TIMESTAMP_SIZE
        if payload_size > MAX_I_PAYLOAD_SIZE:
            raise Awg31ValidationError(
                f"{name} expanded payload exceeds the AWG31 MTU-safe limit"
            )
        position = match.end()
    return text, payload_size


def validate_parameters(values: Mapping[str, object]) -> dict[str, str | int]:
    unknown = set(values) - set(FIELD_NAMES)
    if unknown:
        raise Awg31ValidationError("Unknown AWG31 fields: " + ", ".join(sorted(unknown)))
    result: dict[str, str | int] = {}
    total_i_payload = 0
    for name in I_FIELDS:
        tagged, payload_size = _tagged_junk(
            name, values.get(name, DEFAULT_PARAMETERS[name])
        )
        result[name] = tagged
        total_i_payload += payload_size
    if total_i_payload > MAX_I_PAYLOAD_SIZE:
        raise Awg31ValidationError(
            "Combined I1-I5 payload exceeds the AWG31 MTU-safe limit"
        )
    for name in J_FIELDS + S_FIELDS:
        result[name] = _uint16(name, values.get(name, DEFAULT_PARAMETERS[name]))

    header_ranges: dict[str, tuple[int, int]] = {}
    for name in H_FIELDS:
        normalized, low, high = _u32_range_parts(
            name, values.get(name, DEFAULT_PARAMETERS[name])
        )
        result[name] = normalized
        header_ranges[name] = (low, high)
    for index, left_name in enumerate(H_FIELDS):
        left_low, left_high = header_ranges[left_name]
        for right_name in H_FIELDS[index + 1 :]:
            right_low, right_high = header_ranges[right_name]
            if max(left_low, right_low) <= min(left_high, right_high):
                raise Awg31ValidationError(
                    f"{left_name} and {right_name} header ranges must not overlap"
                )

    if int(result["Jmin"]) > int(result["Jmax"]):
        raise Awg31ValidationError("Jmin must not exceed Jmax")
    return result


def _storage_config(parameters: Mapping[str, str | int], server_public_key: str = "") -> dict:
    return {
        "profile": PROFILE_ID,
        "generation": 31,
        "dns": DNS,
        "transport": TRANSPORT,
        "endpoint": ENDPOINT,
        "server_public_key": server_public_key,
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
    parameters = validate_parameters(normalize_legacy_parameters(raw))
    return Awg31Settings(
        parameters=parameters,
        server_public_key=str(config.get("server_public_key") or ""),
        enabled=bool(row["enabled"]),
    )


def save_settings(values: Mapping[str, object]) -> Awg31Settings:
    current = get_settings()
    merged = dict(current.parameters)
    merged.update(values)
    parameters = validate_parameters(merged)
    config = _storage_config(parameters, current.server_public_key)
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
            peer.update(_storage_config(parameters, current.server_public_key))
            connection.execute(
                "UPDATE device_credentials SET config_json = ?, status = 'pending' WHERE id = ?",
                (json.dumps(peer, ensure_ascii=False, sort_keys=True), int(row["id"])),
            )
    return get_settings()


def set_server_public_key(value: str) -> None:
    current = get_settings()
    key = str(value or "").strip()
    config = _storage_config(current.parameters, key)
    with connect() as connection:
        connection.execute(
            "UPDATE connection_settings SET config_json = ?, updated_at = CURRENT_TIMESTAMP WHERE engine = ?",
            (json.dumps(config, ensure_ascii=False, sort_keys=True), ENGINE_ID),
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
            peer["server_public_key"] = key
            connection.execute(
                "UPDATE device_credentials SET config_json = ? WHERE id = ?",
                (json.dumps(peer, ensure_ascii=False, sort_keys=True), int(row["id"])),
            )


def config_lines(settings: Awg31Settings | None = None) -> list[str]:
    current = settings or get_settings()
    lines: list[str] = []
    for name in FIELD_NAMES:
        value = current.parameters[name]
        if name in I_FIELDS and value == "":
            continue
        lines.append(f"{name} = {value}")
    return lines
