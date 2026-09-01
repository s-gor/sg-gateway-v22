from __future__ import annotations

import argparse
import grp
import http.client
import ipaddress
import json
import os
import pwd
import re
import socket
import socketserver
import struct
import uuid
from dataclasses import dataclass
from datetime import datetime
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit

DEFAULT_SOCKET = Path("/run/sg-infosec-bridge/management.sock")
DEFAULT_UPSTREAM_SOCKET = Path("/run/sg-infosec/control.sock")
DEFAULT_MAX_REQUEST_BYTES = 16 * 1024
DEFAULT_MAX_RESPONSE_BYTES = 64 * 1024
DEFAULT_TIMEOUT_SECONDS = 0.75
DEFAULT_MAX_DURATION_HOURS = 168
_ALLOWED_SCOPES = frozenset({"admin-login", "admin-api", "ssh"})
_IDENTIFIER = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_DURATION = re.compile(r"^(?P<value>[1-9][0-9]*)(?P<unit>[mh])$")


@dataclass(frozen=True)
class BridgePolicy:
    allowed_uid: int
    max_request_bytes: int = DEFAULT_MAX_REQUEST_BYTES
    max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    max_duration_hours: int = DEFAULT_MAX_DURATION_HOURS

    def __post_init__(self) -> None:
        if self.allowed_uid < 0:
            raise ValueError("allowed_uid must be non-negative")
        if not 1024 <= self.max_request_bytes <= 1024 * 1024:
            raise ValueError("max_request_bytes is outside the safe range")
        if not 1024 <= self.max_response_bytes <= 4 * 1024 * 1024:
            raise ValueError("max_response_bytes is outside the safe range")
        if not 0.05 <= self.timeout_seconds <= 5.0:
            raise ValueError("timeout_seconds is outside the safe range")
        if not 1 <= self.max_duration_hours <= 168:
            raise ValueError("max_duration_hours is outside the safe range")


class BridgeRequestError(ValueError):
    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def authorize_peer(peer_uid: int, policy: BridgePolicy) -> bool:
    return int(peer_uid) == policy.allowed_uid


def _require_mapping(payload: object) -> dict[str, Any]:
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise BridgeRequestError("invalid_json", "JSON object is required")
    return payload


def _canonical_ip(value: object) -> str:
    try:
        address = ipaddress.ip_address(str(value or "").strip())
    except ValueError as exc:
        raise BridgeRequestError("invalid_ip", "valid IPv4 or IPv6 address is required") from exc
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        return str(address.ipv4_mapped)
    return address.compressed


def _canonical_prefix(value: object) -> str:
    try:
        network = ipaddress.ip_network(str(value or "").strip(), strict=False)
    except ValueError as exc:
        raise BridgeRequestError("invalid_prefix", "valid IP address or CIDR is required") from exc
    return network.compressed


def _scope(value: object, *, optional: bool = False) -> str:
    text = str(value or "").strip()
    if optional and not text:
        return ""
    if text not in _ALLOWED_SCOPES:
        raise BridgeRequestError("invalid_scope", "scope is not allowed")
    return text


def _reason(value: object, field: str = "reason") -> str:
    text = " ".join(str(value or "").split())
    if not 3 <= len(text) <= 240:
        raise BridgeRequestError(f"invalid_{field}", f"{field} must contain 3 to 240 characters")
    return text


def _duration(value: object, policy: BridgePolicy) -> str:
    text = str(value or "").strip().lower()
    match = _DURATION.fullmatch(text)
    if match is None:
        raise BridgeRequestError("invalid_duration", "duration must use minutes or hours")
    amount = int(match.group("value"))
    seconds = amount * (60 if match.group("unit") == "m" else 3600)
    if seconds > policy.max_duration_hours * 3600:
        raise BridgeRequestError("invalid_duration", "duration exceeds the configured maximum")
    return text


def _identifier(value: str, kind: str) -> str:
    if not _IDENTIFIER.fullmatch(value):
        raise BridgeRequestError(f"invalid_{kind}_id", f"{kind} identifier is invalid")
    return value


def _expires_at(value: object) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise BridgeRequestError("invalid_expires_at", "expires_at must be an ISO-8601 timestamp") from exc
    return text


def _single_query(parsed, allowed: set[str]) -> dict[str, str]:
    raw = parse_qs(parsed.query, keep_blank_values=False, strict_parsing=False)
    if set(raw) - allowed:
        raise BridgeRequestError("invalid_query", "query parameter is not allowed")
    result: dict[str, str] = {}
    for key, values in raw.items():
        if len(values) != 1:
            raise BridgeRequestError("invalid_query", "query parameter must occur once")
        result[key] = values[0]
    return result


def _list_target(path: str, parsed) -> str:
    if path == "/v1/decisions":
        query = _single_query(parsed, {"state", "scope", "source_id", "limit", "cursor"})
        if "state" in query and query["state"] not in {"active", "revoked", "expired"}:
            raise BridgeRequestError("invalid_state", "decision state is not allowed")
        if "scope" in query:
            query["scope"] = _scope(query["scope"])
        if "source_id" in query and query["source_id"] != "sg-gateway":
            raise BridgeRequestError("invalid_source_id", "source filter is not allowed")
    elif path == "/v1/allowlist":
        query = _single_query(parsed, {"scope", "limit", "cursor"})
        if "scope" in query:
            query["scope"] = _scope(query["scope"])
    elif path == "/v1/audit":
        query = _single_query(parsed, {"actor", "action", "limit", "cursor"})
        if "actor" in query and query["actor"] not in {"sg-gateway", "sg-gateway-management"}:
            raise BridgeRequestError("invalid_actor", "actor filter is not allowed")
    else:
        raise BridgeRequestError("route_not_allowed", "management route is not allowed", 404)
    if "limit" in query:
        try:
            limit = int(query["limit"])
        except ValueError as exc:
            raise BridgeRequestError("invalid_limit", "limit must be an integer") from exc
        if not 1 <= limit <= 100:
            raise BridgeRequestError("invalid_limit", "limit must be between 1 and 100")
        query["limit"] = str(limit)
    encoded = urlencode(query)
    return path if not encoded else f"{path}?{encoded}"


def build_forward_request(
    method: str,
    target: str,
    payload: object,
    policy: BridgePolicy,
) -> tuple[str, str, dict[str, Any] | None]:
    verb = str(method or "").upper()
    if len(target) > 2048:
        raise BridgeRequestError("target_too_long", "request target is too long")
    parsed = urlsplit(target)
    if parsed.scheme or parsed.netloc or not parsed.path.startswith("/"):
        raise BridgeRequestError("invalid_target", "absolute URLs are forbidden")
    path = parsed.path

    if verb == "GET" and path == "/v1/health" and not parsed.query:
        return "GET", "/v1/decisions?state=active&limit=1", None
    if verb == "GET" and path in {"/v1/decisions", "/v1/allowlist", "/v1/audit"}:
        return "GET", _list_target(path, parsed), None
    if parsed.query:
        raise BridgeRequestError("invalid_query", "query parameters are forbidden for this route")

    body = _require_mapping(payload)
    if verb == "POST" and path == "/v1/decisions/manual":
        scope = _scope(body.get("scope"))
        normalized = {
            "source_id": "sg-gateway",
            "scope": scope,
            "backend": "nftables" if scope == "ssh" else "application",
            "ip": _canonical_ip(body.get("ip")),
            "duration": _duration(body.get("duration"), policy),
            "reason": _reason(body.get("reason")),
            "override_allowlist": bool(body.get("override_allowlist", False)),
        }
        return "POST", path, normalized

    decision_match = re.fullmatch(r"/v1/decisions/([^/]+)/revoke", path)
    if verb == "POST" and decision_match:
        decision_id = _identifier(decision_match.group(1), "decision")
        return "POST", f"/v1/decisions/{decision_id}/revoke", None

    if verb == "POST" and path == "/v1/allowlist":
        normalized = {
            "prefix": _canonical_prefix(body.get("prefix")),
            "scope": _scope(body.get("scope"), optional=True),
            "description": _reason(body.get("description"), "description"),
        }
        expiry = _expires_at(body.get("expires_at"))
        if expiry is not None:
            normalized["expires_at"] = expiry
        return "POST", path, normalized

    allowlist_match = re.fullmatch(r"/v1/allowlist/([^/]+)/delete", path)
    if verb == "POST" and allowlist_match:
        entry_id = _identifier(allowlist_match.group(1), "allowlist")
        return "DELETE", f"/v1/allowlist/{entry_id}", None

    raise BridgeRequestError("route_not_allowed", "management route is not allowed", 404)


class _UnixHTTPConnection(http.client.HTTPConnection):
    def __init__(self, socket_path: Path, timeout: float) -> None:
        super().__init__(host="localhost", timeout=timeout)
        self._socket_path = str(socket_path)

    def connect(self) -> None:
        connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            connection.settimeout(self.timeout)
            connection.connect(self._socket_path)
        except OSError:
            connection.close()
            raise
        self.sock = connection


def _forward(
    upstream_socket: Path,
    method: str,
    target: str,
    payload: dict[str, Any] | None,
    policy: BridgePolicy,
) -> tuple[int, dict[str, Any]]:
    connection = _UnixHTTPConnection(upstream_socket, policy.timeout_seconds)
    encoded = None
    headers = {
        "Accept": "application/json",
        "X-Request-ID": f"sg-gateway-management.{uuid.uuid4().hex}",
    }
    if payload is not None:
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        headers["Content-Type"] = "application/json"
    try:
        connection.request(method, target, body=encoded, headers=headers)
        response = connection.getresponse()
        raw = response.read(policy.max_response_bytes + 1)
        if len(raw) > policy.max_response_bytes:
            raise BridgeRequestError("upstream_response_too_large", "SG-InfoSec response is too large", 502)
        decoded = json.loads(raw.decode("utf-8")) if raw else {}
        if not isinstance(decoded, dict):
            raise BridgeRequestError("invalid_upstream_response", "SG-InfoSec returned invalid JSON", 502)
        return response.status, decoded
    except (OSError, TimeoutError, UnicodeError, json.JSONDecodeError, http.client.HTTPException) as exc:
        raise BridgeRequestError("upstream_unavailable", "SG-InfoSec management is unavailable", 503) from exc
    finally:
        connection.close()


class ManagementRequestHandler(BaseHTTPRequestHandler):
    server_version = "SGInfoSecManagementBridge/1"
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: object) -> None:
        return

    def do_GET(self) -> None:
        self._dispatch()

    def do_POST(self) -> None:
        self._dispatch()

    def do_PUT(self) -> None:
        self._error(405, "method_not_allowed", "method is not allowed")

    def do_PATCH(self) -> None:
        self._error(405, "method_not_allowed", "method is not allowed")

    def do_DELETE(self) -> None:
        self._error(405, "method_not_allowed", "method is not allowed")

    def _peer_uid(self) -> int:
        size = struct.calcsize("3i")
        raw = self.connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, size)
        _pid, uid, _gid = struct.unpack("3i", raw)
        return int(uid)

    def _read_payload(self) -> dict[str, Any] | None:
        length_text = self.headers.get("Content-Length", "0")
        try:
            length = int(length_text)
        except ValueError as exc:
            raise BridgeRequestError("invalid_content_length", "Content-Length is invalid") from exc
        if length < 0 or length > self.server.policy.max_request_bytes:
            raise BridgeRequestError("request_too_large", "request body is too large", 413)
        if length == 0:
            return None
        content_type = self.headers.get_content_type()
        if content_type != "application/json":
            raise BridgeRequestError("invalid_content_type", "application/json is required", 415)
        raw = self.rfile.read(length)
        try:
            decoded = json.loads(raw.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise BridgeRequestError("invalid_json", "request body is invalid JSON") from exc
        if not isinstance(decoded, dict):
            raise BridgeRequestError("invalid_json", "JSON object is required")
        return decoded

    def _dispatch(self) -> None:
        request_id = f"bridge.{uuid.uuid4().hex}"
        try:
            if not authorize_peer(self._peer_uid(), self.server.policy):
                raise BridgeRequestError("peer_not_allowed", "calling Unix peer is not allowed", 403)
            payload = self._read_payload()
            health_request = self.command == "GET" and self.path == "/v1/health"
            method, target, normalized = build_forward_request(
                self.command,
                self.path,
                payload,
                self.server.policy,
            )
            status, response = _forward(
                self.server.upstream_socket,
                method,
                target,
                normalized,
                self.server.policy,
            )
            if health_request and status == 200:
                response = {"ok": True, "request_id": request_id}
            self._json(status, response)
        except BridgeRequestError as exc:
            self._error(exc.status_code, exc.code, exc.message, request_id=request_id)
        except Exception:
            self._error(500, "internal_error", "management bridge failed", request_id=request_id)

    def _error(self, status: int, code: str, message: str, *, request_id: str | None = None) -> None:
        self._json(
            status,
            {"code": code, "message": message, "request_id": request_id or f"bridge.{uuid.uuid4().hex}"},
        )

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(encoded)


class ManagementUnixServer(socketserver.ThreadingUnixStreamServer):
    address_family = socket.AF_UNIX
    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self,
        socket_path: str | os.PathLike[str],
        handler_class: type[BaseHTTPRequestHandler],
        *,
        policy: BridgePolicy,
        upstream_socket: str | os.PathLike[str],
    ) -> None:
        self.policy = policy
        self.upstream_socket = Path(upstream_socket)
        super().__init__(str(socket_path), handler_class)


def serve(
    *,
    socket_path: Path,
    upstream_socket: Path,
    allowed_user: str,
    socket_group: str,
    max_request_bytes: int = DEFAULT_MAX_REQUEST_BYTES,
    max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    max_duration_hours: int = DEFAULT_MAX_DURATION_HOURS,
) -> None:
    allowed_uid = pwd.getpwnam(allowed_user).pw_uid
    socket_gid = grp.getgrnam(socket_group).gr_gid
    socket_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        socket_path.unlink()
    except FileNotFoundError:
        pass
    policy = BridgePolicy(
        allowed_uid=allowed_uid,
        max_request_bytes=max_request_bytes,
        max_response_bytes=max_response_bytes,
        timeout_seconds=timeout_seconds,
        max_duration_hours=max_duration_hours,
    )
    with ManagementUnixServer(
        socket_path,
        ManagementRequestHandler,
        policy=policy,
        upstream_socket=upstream_socket,
    ) as server:
        os.chown(socket_path, -1, socket_gid)
        os.chmod(socket_path, 0o660)
        server.serve_forever(poll_interval=0.25)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SG-InfoSec management bridge for SG-Gateway")
    parser.add_argument("--socket", default=str(DEFAULT_SOCKET))
    parser.add_argument("--upstream-socket", default=str(DEFAULT_UPSTREAM_SOCKET))
    parser.add_argument("--allowed-user", default="sg-gateway")
    parser.add_argument("--socket-group", default="sg-gateway")
    parser.add_argument("--max-request-bytes", type=int, default=DEFAULT_MAX_REQUEST_BYTES)
    parser.add_argument("--max-response-bytes", type=int, default=DEFAULT_MAX_RESPONSE_BYTES)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--max-duration-hours", type=int, default=DEFAULT_MAX_DURATION_HOURS)
    args = parser.parse_args(argv)
    serve(
        socket_path=Path(args.socket),
        upstream_socket=Path(args.upstream_socket),
        allowed_user=args.allowed_user,
        socket_group=args.socket_group,
        max_request_bytes=args.max_request_bytes,
        max_response_bytes=args.max_response_bytes,
        timeout_seconds=args.timeout,
        max_duration_hours=args.max_duration_hours,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
