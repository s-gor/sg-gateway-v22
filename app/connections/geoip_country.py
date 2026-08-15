from __future__ import annotations

import functools
import ipaddress
import os
import re
import socket
from pathlib import Path
from typing import Iterable


ISO_ALPHA2_RE = re.compile(r"^[a-z]{2}$")
DEFAULT_GEOIP_PATHS = (
    # Country flags must not depend on the routing GeoFiles family.
    Path("/opt/sg-gateway/assets/geoip/sg-country-geoip.dat"),
    Path("/var/lib/sg-gateway/geoip/sg-country-geoip.dat"),
    Path("/usr/local/share/xray/geoip.dat"),
    Path("/usr/share/xray/geoip.dat"),
)


class GeoIpLookupError(RuntimeError):
    pass


def _read_varint(data: bytes, offset: int) -> tuple[int, int]:
    value = 0
    shift = 0
    while offset < len(data) and shift <= 63:
        byte = data[offset]
        offset += 1
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value, offset
        shift += 7
    raise GeoIpLookupError("Повреждённый protobuf varint")


def _iter_fields(data: bytes) -> Iterable[tuple[int, int, bytes | int]]:
    offset = 0
    while offset < len(data):
        key, offset = _read_varint(data, offset)
        field = key >> 3
        wire = key & 0x07
        if field <= 0:
            raise GeoIpLookupError("Некорректный номер protobuf-поля")
        if wire == 0:
            value, offset = _read_varint(data, offset)
            yield field, wire, value
        elif wire == 1:
            end = offset + 8
            if end > len(data):
                raise GeoIpLookupError("Обрезанное protobuf fixed64")
            yield field, wire, data[offset:end]
            offset = end
        elif wire == 2:
            length, offset = _read_varint(data, offset)
            end = offset + length
            if end > len(data):
                raise GeoIpLookupError("Обрезанное protobuf поле")
            yield field, wire, data[offset:end]
            offset = end
        elif wire == 5:
            end = offset + 4
            if end > len(data):
                raise GeoIpLookupError("Обрезанное protobuf fixed32")
            yield field, wire, data[offset:end]
            offset = end
        else:
            raise GeoIpLookupError(f"Неподдерживаемый wire type: {wire}")


def _decode_country(payload: bytes) -> str | None:
    try:
        value = payload.decode("ascii").strip().lower()
    except UnicodeDecodeError:
        return None
    return value if ISO_ALPHA2_RE.fullmatch(value) else None


def _parse_cidr(payload: bytes) -> tuple[bytes, int] | None:
    address = b""
    prefix = None
    try:
        for field, wire, value in _iter_fields(payload):
            if field == 1 and wire == 2 and isinstance(value, bytes):
                address = value
            elif field == 2 and wire == 0 and isinstance(value, int):
                prefix = value
    except GeoIpLookupError:
        return None
    if len(address) not in (4, 16) or prefix is None:
        return None
    if prefix < 0 or prefix > len(address) * 8:
        return None
    return address, prefix


def _matches(ip: ipaddress._BaseAddress, packed: bytes, prefix: int) -> bool:
    if len(ip.packed) != len(packed):
        return False
    full_bytes, remaining_bits = divmod(prefix, 8)
    if ip.packed[:full_bytes] != packed[:full_bytes]:
        return False
    if remaining_bits == 0:
        return True
    mask = 0xFF & (0xFF << (8 - remaining_bits))
    return (ip.packed[full_bytes] & mask) == (packed[full_bytes] & mask)


def resolve_host_ip(host: str) -> str:
    value = (host or "").strip().strip("[]")
    if not value:
        return ""
    try:
        address = ipaddress.ip_address(value)
        return str(address) if address.is_global else ""
    except ValueError:
        pass

    try:
        results = socket.getaddrinfo(value, None, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return ""

    candidates: list[ipaddress._BaseAddress] = []
    for result in results:
        raw = result[4][0].split("%", 1)[0]
        try:
            address = ipaddress.ip_address(raw)
        except ValueError:
            continue
        if address.is_global:
            candidates.append(address)

    candidates.sort(key=lambda item: 0 if item.version == 4 else 1)
    return str(candidates[0]) if candidates else ""


def active_geoip_path() -> Path | None:
    override = os.getenv("SG_GATEWAY_GEOIP_PATH", "").strip()
    candidates = (Path(override),) if override else DEFAULT_GEOIP_PATHS
    for path in candidates:
        if path.is_file() and path.stat().st_size > 1024:
            return path
    return None


@functools.lru_cache(maxsize=128)
def _lookup_cached(ip_text: str, path_text: str, mtime_ns: int, size: int) -> str:
    del mtime_ns, size
    ip = ipaddress.ip_address(ip_text)
    data = Path(path_text).read_bytes()

    for _outer_field, wire, entry_payload in _iter_fields(data):
        if wire != 2 or not isinstance(entry_payload, bytes):
            continue

        country = None
        cidrs: list[tuple[bytes, int]] = []
        try:
            for field, inner_wire, value in _iter_fields(entry_payload):
                if field == 1 and inner_wire == 2 and isinstance(value, bytes):
                    country = _decode_country(value)
                elif field == 2 and inner_wire == 2 and isinstance(value, bytes):
                    parsed = _parse_cidr(value)
                    if parsed is not None:
                        cidrs.append(parsed)
        except GeoIpLookupError:
            continue

        if country is None:
            continue

        for packed, prefix in cidrs:
            if _matches(ip, packed, prefix):
                return country

    return "unknown"


def lookup_country_code(host_or_ip: str) -> str:
    ip_text = resolve_host_ip(host_or_ip)
    if not ip_text:
        return "unknown"
    path = active_geoip_path()
    if path is None:
        return "unknown"
    try:
        stat = path.stat()
        return _lookup_cached(ip_text, str(path), stat.st_mtime_ns, stat.st_size)
    except (OSError, ValueError, GeoIpLookupError):
        return "unknown"
