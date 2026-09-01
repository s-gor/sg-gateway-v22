from __future__ import annotations

import http.client
import ipaddress
import json
import os
import socket
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

DEFAULT_CONTROL_SOCKET = Path("/run/sg-infosec/control.sock")
DEFAULT_EVENTS_SOCKET = Path("/run/sg-infosec/events.sock")
DEFAULT_TIMEOUT_SECONDS = 0.2
MAX_RESPONSE_BYTES = 64 * 1024
_FORBIDDEN_METADATA_KEYS = frozenset(
    {
        "password",
        "passwd",
        "token",
        "authorization",
        "cookie",
        "private_key",
        "subscription_url",
        "config",
    }
)


class _UnixHTTPConnection(http.client.HTTPConnection):
    """HTTP/1.1 connection that can only dial one Unix domain socket."""

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


def _canonical_ip(value: object) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        address = ipaddress.ip_address(text)
    except ValueError:
        return None
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        return str(address.ipv4_mapped)
    return address.compressed


def client_ip_from_request(request: Any) -> str:
    """Resolve a client IP without trusting headers from direct remote peers.

    SG-Gateway's Nginx configuration overwrites X-Real-IP with $remote_addr and
    appends $remote_addr to X-Forwarded-For. Those headers are accepted only
    when the immediate WSGI peer is loopback.
    """

    peer = _canonical_ip(getattr(request, "remote_addr", None))
    if peer is None:
        return ""

    peer_address = ipaddress.ip_address(peer)
    if not peer_address.is_loopback:
        return peer

    headers = getattr(request, "headers", {})
    real_ip = _canonical_ip(headers.get("X-Real-IP"))
    if real_ip is not None:
        return real_ip

    forwarded = str(headers.get("X-Forwarded-For", ""))
    for item in reversed(forwarded.split(",")):
        candidate = _canonical_ip(item)
        if candidate is not None:
            return candidate
    return peer


def classify_request(
    endpoint: str | None,
    method: str,
    path: str,
    public_endpoints: Iterable[str],
    login_endpoint: str,
    admin_api_prefixes: tuple[str, ...],
) -> str | None:
    endpoint_name = str(endpoint or "")
    if endpoint_name == login_endpoint and method.upper() == "POST":
        return "admin-login"
    if endpoint_name in set(public_endpoints) or endpoint_name.startswith("static"):
        return None
    if any(path.startswith(prefix) for prefix in admin_api_prefixes):
        return "admin-api"
    return None


def should_emit_auth_failure(
    scope: str | None,
    status_code: int,
    *,
    api_auth_failed: bool = False,
) -> bool:
    if status_code != 401:
        return False
    if scope == "admin-login":
        return True
    return scope == "admin-api" and api_auth_failed


def _safe_route(route: object) -> str:
    text = str(route or "unknown").strip()
    if not text:
        return "unknown"
    allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._:-"
    cleaned = "".join(character if character in allowed else "_" for character in text)
    return cleaned[:128] or "unknown"


def _safe_metadata(value: Any, *, depth: int = 0) -> Any:
    if depth > 6:
        raise ValueError("metadata nesting is too deep")
    if value is None or isinstance(value, (str, bool, float, int)):
        if isinstance(value, str):
            return value[:512]
        return value
    if isinstance(value, list):
        if len(value) > 32:
            raise ValueError("metadata list is too large")
        return [_safe_metadata(item, depth=depth + 1) for item in value]
    if isinstance(value, dict):
        if len(value) > 32:
            raise ValueError("metadata object is too large")
        result: dict[str, Any] = {}
        for raw_key, child in value.items():
            key = str(raw_key)[:64]
            if key.lower() in _FORBIDDEN_METADATA_KEYS:
                raise ValueError("sensitive metadata key is forbidden")
            result[key] = _safe_metadata(child, depth=depth + 1)
        return result
    raise ValueError("unsupported metadata value")


def build_security_event(
    *,
    scope: str,
    ip: str,
    route: str,
    metadata: dict[str, Any],
    subject: str | None = None,
) -> dict[str, Any]:
    canonical_ip = _canonical_ip(ip)
    if canonical_ip is None:
        raise ValueError("invalid client IP")
    if scope not in {"admin-login", "admin-api"}:
        raise ValueError("unsupported SG InfoSec scope")
    safe_metadata = _safe_metadata(metadata)
    if not isinstance(safe_metadata, dict):
        raise ValueError("metadata must be an object")
    safe_metadata["route"] = _safe_route(route)
    event: dict[str, Any] = {
        "event_id": f"sg-gateway-{uuid.uuid4().hex}",
        "event_type": "auth.failed" if scope == "admin-login" else "api.auth_failed",
        "scope": scope,
        "ip": canonical_ip,
        "occurred_at": datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z"),
        "metadata": safe_metadata,
    }
    if subject:
        event["subject"] = _safe_route(subject)
    return event


def build_auth_failure_event(
    *,
    scope: str,
    ip: str,
    route: str,
    subject: str | None = None,
) -> dict[str, Any]:
    return build_security_event(
        scope=scope,
        ip=ip,
        route=route,
        subject=subject,
        metadata={"reason": "invalid_credentials"},
    )


class SGInfoSecClient:
    """Small fail-open client for SG InfoSec local protocol v1."""

    def __init__(
        self,
        control_socket: str | os.PathLike[str] = DEFAULT_CONTROL_SOCKET,
        events_socket: str | os.PathLike[str] = DEFAULT_EVENTS_SOCKET,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self.control_socket = Path(control_socket)
        self.events_socket = Path(events_socket)
        self.timeout = max(0.01, min(float(timeout), 2.0))

    @classmethod
    def from_environment(cls) -> "SGInfoSecClient":
        timeout_text = os.environ.get("SG_INFOSEC_TIMEOUT_SECONDS", "").strip()
        try:
            timeout = float(timeout_text) if timeout_text else DEFAULT_TIMEOUT_SECONDS
        except ValueError:
            timeout = DEFAULT_TIMEOUT_SECONDS
        return cls(
            control_socket=os.environ.get(
                "SG_INFOSEC_CONTROL_SOCKET", str(DEFAULT_CONTROL_SOCKET)
            ),
            events_socket=os.environ.get(
                "SG_INFOSEC_EVENTS_SOCKET", str(DEFAULT_EVENTS_SOCKET)
            ),
            timeout=timeout,
        )

    def _post_json(
        self,
        socket_path: Path,
        target: str,
        payload: dict[str, Any],
    ) -> tuple[int, dict[str, Any]] | None:
        connection = _UnixHTTPConnection(socket_path, self.timeout)
        try:
            encoded = json.dumps(
                payload,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
            connection.request(
                "POST",
                target,
                body=encoded,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "X-Request-ID": f"sg-gateway.{uuid.uuid4().hex}",
                },
            )
            response = connection.getresponse()
            body = response.read(MAX_RESPONSE_BYTES + 1)
            if len(body) > MAX_RESPONSE_BYTES:
                return None
            decoded = json.loads(body.decode("utf-8"))
            if not isinstance(decoded, dict):
                return None
            return response.status, decoded
        except (
            OSError,
            TimeoutError,
            ValueError,
            UnicodeError,
            http.client.HTTPException,
        ):
            return None
        finally:
            connection.close()

    def is_blocked(self, *, scope: str, ip: str, route_id: str) -> bool:
        canonical_ip = _canonical_ip(ip)
        if canonical_ip is None or scope not in {"admin-login", "admin-api"}:
            return False
        result = self._post_json(
            self.control_socket,
            "/v1/decisions/check",
            {
                "scope": scope,
                "ip": canonical_ip,
                "route_id": _safe_route(route_id),
            },
        )
        if result is None:
            return False
        status, payload = result
        return status == 200 and payload.get("blocked") is True

    def emit_security_event(
        self,
        *,
        scope: str,
        ip: str,
        route: str,
        metadata: dict[str, Any],
        subject: str | None = None,
    ) -> bool:
        try:
            event = build_security_event(
                scope=scope,
                ip=ip,
                route=route,
                metadata=metadata,
                subject=subject,
            )
        except ValueError:
            return False
        result = self._post_json(self.events_socket, "/v1/events", event)
        if result is None:
            return False
        status, payload = result
        return status in {200, 202} and payload.get("accepted") is True

    def emit_auth_failure(
        self,
        *,
        scope: str,
        ip: str,
        route: str,
        subject: str | None = None,
    ) -> bool:
        return self.emit_security_event(
            scope=scope,
            ip=ip,
            route=route,
            subject=subject,
            metadata={"reason": "invalid_credentials"},
        )


def register_sg_infosec(
    app: Any,
    *,
    client: SGInfoSecClient | None = None,
    public_endpoints: set[str] | None = None,
    login_endpoint: str = "login_post",
    admin_api_prefixes: tuple[str, ...] = ("/api/",),
) -> None:
    """Attach SG InfoSec middleware ahead of SG-Gateway's auth hook."""

    if "sg_infosec" in app.extensions:
        return

    if public_endpoints is None:
        from app.security.auth import PUBLIC_ENDPOINTS

        public_endpoints = set(PUBLIC_ENDPOINTS)
    else:
        public_endpoints = set(public_endpoints)
    adapter_client = client or SGInfoSecClient.from_environment()

    @app.before_request
    def _sg_infosec_before_request():
        from flask import g, jsonify, request

        scope = classify_request(
            request.endpoint,
            request.method,
            request.path,
            public_endpoints,
            login_endpoint,
            admin_api_prefixes,
        )
        if scope is None:
            return None

        ip = client_ip_from_request(request)
        route = request.endpoint or "unknown"
        g.sg_infosec_scope = scope
        g.sg_infosec_ip = ip
        g.sg_infosec_route = route
        g.sg_infosec_api_auth_failed = False

        if adapter_client.is_blocked(scope=scope, ip=ip, route_id=route):
            response = jsonify({"error": "temporarily_blocked"})
            response.status_code = 429
            return response

        if scope == "admin-api":
            from app.security.auth import is_authenticated

            if not is_authenticated():
                g.sg_infosec_api_auth_failed = True
                response = jsonify({"error": "authentication_required"})
                response.status_code = 401
                return response
        return None

    before_handlers = app.before_request_funcs.get(None, [])
    if before_handlers and before_handlers[-1] is _sg_infosec_before_request:
        before_handlers.insert(0, before_handlers.pop())

    @app.after_request
    def _sg_infosec_after_request(response):
        from flask import g

        scope = getattr(g, "sg_infosec_scope", None)
        api_auth_failed = bool(
            getattr(g, "sg_infosec_api_auth_failed", False)
        )
        if should_emit_auth_failure(
            scope,
            int(response.status_code),
            api_auth_failed=api_auth_failed,
        ):
            adapter_client.emit_auth_failure(
                scope=scope,
                ip=getattr(g, "sg_infosec_ip", ""),
                route=getattr(g, "sg_infosec_route", "unknown"),
                subject="admin" if scope == "admin-login" else None,
            )
        return response

    app.extensions["sg_infosec"] = {
        "client": adapter_client,
        "public_endpoints": frozenset(public_endpoints),
        "admin_api_prefixes": admin_api_prefixes,
    }
