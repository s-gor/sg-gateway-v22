from __future__ import annotations

import base64
import json
import zlib
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit

from app.connections.awg31 import DNS, FIELD_NAMES, I_FIELDS, validate_parameters

SCHEME = "awg31"
AUTHORITY = "import"
VERSION = "v1"
MAX_TOKEN_SIZE = 65536
MAX_DECODED_SIZE = 131072


class Awg31UriError(ValueError):
    pass


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    try:
        return base64.b64decode(value + padding, altchars=b"-_", validate=True)
    except (ValueError, TypeError) as exc:
        raise Awg31UriError("Invalid AWG31 URI payload encoding") from exc


def _endpoint(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        raise Awg31UriError("AWG31 URI requires an endpoint")
    try:
        parsed = urlsplit(f"//{text}")
        port = parsed.port
    except ValueError as exc:
        raise Awg31UriError("AWG31 URI endpoint is invalid") from exc
    if (
        not parsed.hostname
        or port is None
        or not 1 <= port <= 65535
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or parsed.username
        or parsed.password
    ):
        raise Awg31UriError("AWG31 URI endpoint is invalid")
    return text


def _validate_config(payload: Mapping[str, Any], parameters: Mapping[str, str | int]) -> str:
    endpoint = _endpoint(payload.get("endpoint"))
    config = payload.get("config")
    if not isinstance(config, str) or not config or len(config) > MAX_DECODED_SIZE:
        raise Awg31UriError("AWG31 URI does not contain a valid configuration")
    required_lines = (
        f"PrivateKey = {payload['private_key']}",
        f"PublicKey = {payload['public_key']}",
        f"Endpoint = {endpoint}",
        f"DNS = {DNS}",
    )
    for line in required_lines:
        if line not in config:
            raise Awg31UriError(f"AWG31 URI configuration is missing {line.split(' =', 1)[0]}")
    for name in FIELD_NAMES:
        value = parameters[name]
        line = f"{name} = {value}"
        if name in I_FIELDS and value == "":
            if f"{name} =" in config:
                raise Awg31UriError(f"Empty {name} must be omitted")
        elif line not in config:
            raise Awg31UriError(f"AWG31 URI configuration is missing {name}")
    return config


def encode_awg31_uri(payload: Mapping[str, Any]) -> str:
    parameters_raw = payload.get("parameters")
    if not isinstance(parameters_raw, Mapping):
        raise Awg31UriError("AWG31 URI parameters must be an object")
    parameters = validate_parameters(parameters_raw)
    normalized = {
        "profile": "awg31",
        "version": 1,
        "endpoint": _endpoint(payload.get("endpoint")),
        "transport": "udp",
        "dns": DNS,
        "private_key": str(payload.get("private_key") or ""),
        "public_key": str(payload.get("public_key") or ""),
        "address": str(payload.get("address") or ""),
        "allowed_ips": str(payload.get("allowed_ips") or "0.0.0.0/0, ::/0"),
        "persistent_keepalive": int(payload.get("persistent_keepalive") or 25),
        "parameters": parameters,
        "config": str(payload.get("config") or ""),
    }
    if not normalized["private_key"] or not normalized["public_key"]:
        raise Awg31UriError("AWG31 URI requires both client and server keys")
    normalized["config"] = _validate_config(normalized, parameters)
    encoded = json.dumps(
        normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    token = _b64encode(zlib.compress(encoded, level=9))
    if len(token) > MAX_TOKEN_SIZE:
        raise Awg31UriError("AWG31 URI payload is too large")
    return f"{SCHEME}://{AUTHORITY}/{VERSION}/{token}"


def decode_awg31_uri(uri: str) -> dict[str, Any]:
    parsed = urlsplit(str(uri))
    if parsed.scheme != SCHEME or parsed.netloc != AUTHORITY:
        raise Awg31UriError("Unsupported AWG31 URI")
    parts = parsed.path.strip("/").split("/", 1)
    if len(parts) != 2 or parts[0] != VERSION or not parts[1]:
        raise Awg31UriError("Unsupported AWG31 URI version")
    token = parts[1]
    if len(token) > MAX_TOKEN_SIZE:
        raise Awg31UriError("AWG31 URI payload is too large")
    compressed = _b64decode(token)
    decompressor = zlib.decompressobj()
    decoded = decompressor.decompress(compressed, MAX_DECODED_SIZE + 1)
    decoded += decompressor.flush()
    if len(decoded) > MAX_DECODED_SIZE or decompressor.unconsumed_tail:
        raise Awg31UriError("AWG31 URI payload expands beyond the safe limit")
    try:
        payload = json.loads(decoded.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Awg31UriError("Invalid AWG31 URI JSON payload") from exc
    if not isinstance(payload, dict):
        raise Awg31UriError("Invalid AWG31 URI payload")
    if payload.get("profile") != "awg31" or payload.get("version") != 1:
        raise Awg31UriError("AWG31 URI profile/version mismatch")
    payload["endpoint"] = _endpoint(payload.get("endpoint"))
    if payload.get("transport") != "udp" or payload.get("dns") != DNS:
        raise Awg31UriError("AWG31 URI transport or DNS mismatch")
    parameters_raw = payload.get("parameters")
    if not isinstance(parameters_raw, Mapping):
        raise Awg31UriError("AWG31 URI parameters must be an object")
    parameters = validate_parameters(parameters_raw)
    payload["parameters"] = parameters
    payload["config"] = _validate_config(payload, parameters)
    return payload
