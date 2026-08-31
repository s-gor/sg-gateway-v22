from __future__ import annotations

import json
import socket
import sys
import threading
import types
from pathlib import Path
from types import SimpleNamespace

from app.security.sg_infosec import (
    SGInfoSecClient,
    build_auth_failure_event,
    classify_request,
    client_ip_from_request,
    register_sg_infosec,
    should_emit_auth_failure,
)


class UnixHTTPServer:
    def __init__(self, path: Path, responses: list[tuple[int, dict]]) -> None:
        self.path = path
        self.responses = list(responses)
        self.requests: list[dict] = []
        self._thread: threading.Thread | None = None
        self._listener: socket.socket | None = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._listener.bind(str(self.path))
        self._listener.listen(8)
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *_):
        if self._listener is not None:
            self._listener.close()
        if self._thread is not None:
            self._thread.join(timeout=1)
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass

    def _serve(self) -> None:
        assert self._listener is not None
        for status, body in self.responses:
            try:
                conn, _ = self._listener.accept()
            except OSError:
                return
            with conn:
                raw = b""
                while b"\r\n\r\n" not in raw:
                    chunk = conn.recv(4096)
                    if not chunk:
                        break
                    raw += chunk
                head, _, remainder = raw.partition(b"\r\n\r\n")
                lines = head.decode("ascii").split("\r\n")
                method, target, _ = lines[0].split(" ", 2)
                headers = {}
                for line in lines[1:]:
                    key, value = line.split(":", 1)
                    headers[key.lower()] = value.strip()
                length = int(headers.get("content-length", "0"))
                payload = remainder
                while len(payload) < length:
                    payload += conn.recv(length - len(payload))
                self.requests.append({
                    "method": method,
                    "target": target,
                    "headers": headers,
                    "json": json.loads(payload[:length] or b"{}"),
                })
                encoded = json.dumps(body).encode("utf-8")
                reason = "OK" if status < 400 else "Error"
                conn.sendall(
                    f"HTTP/1.1 {status} {reason}\r\n".encode("ascii")
                    + b"Content-Type: application/json\r\n"
                    + f"Content-Length: {len(encoded)}\r\nConnection: close\r\n\r\n".encode("ascii")
                    + encoded
                )


def _request(remote_addr: str, **headers: str):
    return SimpleNamespace(remote_addr=remote_addr, headers=headers)


def test_client_ip_trusts_only_loopback_proxy_and_uses_nginx_real_ip():
    request = _request(
        "127.0.0.1",
        **{
            "X-Real-IP": "203.0.113.7",
            "X-Forwarded-For": "198.51.100.99, 203.0.113.7",
        },
    )
    assert client_ip_from_request(request) == "203.0.113.7"

    spoofed = _request("198.51.100.2", **{"X-Real-IP": "203.0.113.99"})
    assert client_ip_from_request(spoofed) == "198.51.100.2"


def test_client_ip_handles_ipv6_and_malformed_forwarding_safely():
    assert client_ip_from_request(_request("::1", **{"X-Real-IP": "2001:db8::5"})) == "2001:db8::5"
    malformed = _request("127.0.0.1", **{"X-Forwarded-For": "not-an-ip"})
    assert client_ip_from_request(malformed) == "127.0.0.1"
    assert client_ip_from_request(_request("::ffff:192.0.2.4")) == "192.0.2.4"


def test_unix_client_checks_and_emits_without_tcp_fallback(tmp_path, monkeypatch):
    control = tmp_path / "control.sock"
    events = tmp_path / "events.sock"
    tcp_calls = []
    original_socket = socket.socket

    def guarded_socket(family=socket.AF_INET, *args, **kwargs):
        if family in (socket.AF_INET, socket.AF_INET6):
            tcp_calls.append(family)
            raise AssertionError("TCP must not be used")
        return original_socket(family, *args, **kwargs)

    monkeypatch.setattr(socket, "socket", guarded_socket)
    control_responses = [(200, {"blocked": True, "decision_id": "d1"})]
    event_responses = [(202, {"accepted": True, "duplicate": False})]
    with UnixHTTPServer(control, control_responses) as control_server, \
         UnixHTTPServer(events, event_responses) as event_server:
        client = SGInfoSecClient(control_socket=control, events_socket=events, timeout=0.5)
        assert client.is_blocked(
            scope="admin-login", ip="203.0.113.7", route_id="admin.login"
        ) is True
        assert client.emit_auth_failure(
            scope="admin-login", ip="203.0.113.7", route="login_post"
        ) is True

    assert not tcp_calls
    assert control_server.requests[0]["target"] == "/v1/decisions/check"
    assert event_server.requests[0]["target"] == "/v1/events"
    assert event_server.requests[0]["json"]["event_type"] == "auth.failed"


def test_client_fails_open_on_unavailable_daemon(tmp_path):
    missing = tmp_path / "missing.sock"
    client = SGInfoSecClient(control_socket=missing, events_socket=missing, timeout=0.05)
    assert client.is_blocked(scope="admin-login", ip="203.0.113.7", route_id="admin.login") is False
    assert client.emit_auth_failure(
        scope="admin-login", ip="203.0.113.7", route="login_post"
    ) is False


def test_request_classification_excludes_public_subscription_and_vpn_routes():
    public = {"login", "login_post", "subscription_feed"}
    args = (public, "login_post", ("/api/",))
    assert classify_request("login_post", "POST", "/login", *args) == "admin-login"
    assert classify_request("api_status", "GET", "/api/status", *args) == "admin-api"
    assert classify_request(
        "subscription_feed", "GET", "/subscription/token", *args
    ) is None
    assert classify_request("vpn_status", "GET", "/vpn/status", *args) is None
    assert classify_request("login", "GET", "/login", *args) is None
    assert classify_request(
        "sg_subscription_v1", "GET", "/sg/sub/v1/opaque", *args
    ) is None
    assert classify_request(
        "sg_subscription_v1_info",
        "GET",
        "/api/clients/7/sg-subscription-v1",
        *args,
    ) == "admin-api"


def test_failure_event_contains_no_request_secrets():
    event = build_auth_failure_event(
        scope="admin-login",
        ip="203.0.113.9",
        route="login_post",
        subject="admin",
    )
    serialized = json.dumps(event)
    assert event["metadata"] == {"reason": "invalid_credentials", "route": "login_post"}
    forbidden = (
        "password",
        "passwd",
        "token",
        "authorization",
        "cookie",
        "private_key",
        "subscription_url",
        "config",
    )
    for secret in forbidden:
        assert secret not in serialized.lower()


def test_only_login_401_and_admin_api_401_emit_failures():
    assert should_emit_auth_failure("admin-login", 401) is True
    assert should_emit_auth_failure("admin-api", 401) is False
    assert should_emit_auth_failure("admin-api", 401, api_auth_failed=True) is True
    assert should_emit_auth_failure("admin-login", 200) is False
    assert should_emit_auth_failure(None, 401) is False
    assert should_emit_auth_failure("admin-login", 429) is False


class FakeApp:
    def __init__(self):
        self.before_request_funcs = {None: [lambda: "existing-before"]}
        self.after_request_funcs = {None: []}
        self.extensions = {}

    def before_request(self, func):
        self.before_request_funcs.setdefault(None, []).append(func)
        return func

    def after_request(self, func):
        self.after_request_funcs.setdefault(None, []).append(func)
        return func


def test_registration_prepends_guard_before_existing_auth_hook(tmp_path):
    app = FakeApp()
    client = SGInfoSecClient(tmp_path / "control.sock", tmp_path / "events.sock")
    register_sg_infosec(
        app,
        client=client,
        public_endpoints={"login", "login_post", "subscription_feed"},
        login_endpoint="login_post",
        admin_api_prefixes=("/api/",),
    )
    assert app.before_request_funcs[None][0].__name__ == "_sg_infosec_before_request"
    assert app.before_request_funcs[None][1]() == "existing-before"
    assert len(app.after_request_funcs[None]) == 1
    assert app.extensions["sg_infosec"]["client"] is client


class RawUnixHTTPServer:
    def __init__(self, path: Path, response: bytes) -> None:
        self.path = path
        self.response = response
        self._listener: socket.socket | None = None
        self._thread: threading.Thread | None = None

    def __enter__(self):
        self._listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._listener.bind(str(self.path))
        self._listener.listen(1)
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *_):
        if self._listener is not None:
            self._listener.close()
        if self._thread is not None:
            self._thread.join(timeout=1)
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass

    def _serve(self):
        assert self._listener is not None
        try:
            conn, _ = self._listener.accept()
        except OSError:
            return
        with conn:
            conn.recv(65536)
            conn.sendall(self.response)


def test_invalid_or_oversized_control_response_fails_open(tmp_path):
    malformed = tmp_path / "malformed.sock"
    raw = b"not-json"
    response = (
        b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
        + f"Content-Length: {len(raw)}\r\nConnection: close\r\n\r\n".encode("ascii")
        + raw
    )
    with RawUnixHTTPServer(malformed, response):
        client = SGInfoSecClient(control_socket=malformed, events_socket=malformed, timeout=0.5)
        assert client.is_blocked(
            scope="admin-login", ip="203.0.113.7", route_id="admin.login"
        ) is False

    oversized = tmp_path / "oversized.sock"
    raw = json.dumps({"blocked": True, "padding": "x" * 70000}).encode("utf-8")
    response = (
        b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
        + f"Content-Length: {len(raw)}\r\nConnection: close\r\n\r\n".encode("ascii")
        + raw
    )
    with RawUnixHTTPServer(oversized, response):
        client = SGInfoSecClient(control_socket=oversized, events_socket=oversized, timeout=0.5)
        assert client.is_blocked(
            scope="admin-login", ip="203.0.113.7", route_id="admin.login"
        ) is False


def test_non_boolean_blocked_value_is_not_enforced(tmp_path):
    control = tmp_path / "control.sock"
    with UnixHTTPServer(control, [(200, {"blocked": "true"})]):
        client = SGInfoSecClient(control_socket=control, events_socket=tmp_path / "events.sock")
        assert client.is_blocked(
            scope="admin-login", ip="203.0.113.7", route_id="admin.login"
        ) is False


def test_registration_is_idempotent(tmp_path):
    app = FakeApp()
    client = SGInfoSecClient(tmp_path / "control.sock", tmp_path / "events.sock")
    kwargs = {
        "client": client,
        "public_endpoints": {"login", "login_post"},
        "login_endpoint": "login_post",
        "admin_api_prefixes": ("/api/",),
    }
    register_sg_infosec(app, **kwargs)
    before_count = len(app.before_request_funcs[None])
    after_count = len(app.after_request_funcs[None])
    register_sg_infosec(app, **kwargs)
    assert len(app.before_request_funcs[None]) == before_count
    assert len(app.after_request_funcs[None]) == after_count


class FakeResponse:
    def __init__(self, payload=None, status_code=200):
        self.payload = payload
        self.status_code = status_code


class RecordingClient:
    def __init__(self, blocked=False):
        self.blocked = blocked
        self.checks = []
        self.events = []

    def is_blocked(self, **payload):
        self.checks.append(payload)
        return self.blocked

    def emit_auth_failure(self, **payload):
        self.events.append(payload)
        return True


def _install_fake_flask(monkeypatch, request):
    fake_flask = types.ModuleType("flask")
    fake_flask.g = SimpleNamespace()
    fake_flask.request = request
    fake_flask.jsonify = lambda payload: FakeResponse(payload)
    monkeypatch.setitem(sys.modules, "flask", fake_flask)
    return fake_flask


def _install_fake_auth(monkeypatch, authenticated):
    fake_auth = types.ModuleType("app.security.auth")
    fake_auth.is_authenticated = lambda: authenticated
    monkeypatch.setitem(sys.modules, "app.security.auth", fake_auth)


def _registered_hooks(client):
    app = FakeApp()
    register_sg_infosec(
        app,
        client=client,
        public_endpoints={"login", "login_post", "sg_subscription_v1"},
        login_endpoint="login_post",
        admin_api_prefixes=("/api/",),
    )
    return app.before_request_funcs[None][0], app.after_request_funcs[None][0]


def test_middleware_blocks_login_before_credentials(monkeypatch):
    client = RecordingClient(blocked=True)
    before, after = _registered_hooks(client)
    request = SimpleNamespace(
        endpoint="login_post",
        method="POST",
        path="/login",
        remote_addr="127.0.0.1",
        headers={"X-Real-IP": "203.0.113.10"},
    )
    _install_fake_flask(monkeypatch, request)

    response = before()
    response = after(response)

    assert response.status_code == 429
    assert client.checks == [
        {
            "scope": "admin-login",
            "ip": "203.0.113.10",
            "route_id": "login_post",
        }
    ]
    assert client.events == []


def test_middleware_emits_only_after_login_handler_returns_401(monkeypatch):
    client = RecordingClient(blocked=False)
    before, after = _registered_hooks(client)
    request = SimpleNamespace(
        endpoint="login_post",
        method="POST",
        path="/login",
        remote_addr="198.51.100.5",
        headers={"Cookie": "must-not-leak"},
    )
    _install_fake_flask(monkeypatch, request)

    assert before() is None
    response = after(FakeResponse(status_code=401))

    assert response.status_code == 401
    assert client.events == [
        {
            "scope": "admin-login",
            "ip": "198.51.100.5",
            "route": "login_post",
            "subject": "admin",
        }
    ]


def test_middleware_returns_api_401_and_emits_api_failure(monkeypatch):
    client = RecordingClient(blocked=False)
    before, after = _registered_hooks(client)
    request = SimpleNamespace(
        endpoint="api_status",
        method="GET",
        path="/api/status",
        remote_addr="198.51.100.6",
        headers={},
    )
    _install_fake_flask(monkeypatch, request)
    _install_fake_auth(monkeypatch, authenticated=False)

    response = before()
    response = after(response)

    assert response.status_code == 401
    assert response.payload == {"error": "authentication_required"}
    assert client.events == [
        {
            "scope": "admin-api",
            "ip": "198.51.100.6",
            "route": "api_status",
            "subject": None,
        }
    ]


def test_middleware_never_calls_infosec_for_public_subscription(monkeypatch):
    client = RecordingClient(blocked=True)
    before, after = _registered_hooks(client)
    request = SimpleNamespace(
        endpoint="sg_subscription_v1",
        method="GET",
        path="/sg/sub/v1/opaque-secret-token",
        remote_addr="198.51.100.7",
        headers={},
    )
    _install_fake_flask(monkeypatch, request)

    assert before() is None
    response = after(FakeResponse(status_code=200))

    assert response.status_code == 200
    assert client.checks == []
    assert client.events == []


class HangingUnixServer:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._listener: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._release = threading.Event()

    def __enter__(self):
        self._listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._listener.bind(str(self.path))
        self._listener.listen(1)
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *_):
        self._release.set()
        if self._listener is not None:
            self._listener.close()
        if self._thread is not None:
            self._thread.join(timeout=1)
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass

    def _serve(self):
        assert self._listener is not None
        try:
            conn, _ = self._listener.accept()
        except OSError:
            return
        with conn:
            conn.recv(65536)
            self._release.wait(timeout=1)


def test_hanging_daemon_times_out_and_fails_open(tmp_path):
    control = tmp_path / "hanging.sock"
    with HangingUnixServer(control):
        client = SGInfoSecClient(
            control_socket=control,
            events_socket=tmp_path / "events.sock",
            timeout=0.05,
        )
        assert client.is_blocked(
            scope="admin-login",
            ip="203.0.113.7",
            route_id="admin.login",
        ) is False
