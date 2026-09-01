import json
import os
import socket
import socketserver
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler

import pytest

from app.security.sg_infosec_bridge import (
    BridgePolicy,
    BridgeRequestError,
    ManagementRequestHandler,
    ManagementUnixServer,
    authorize_peer,
    build_forward_request,
)


def policy() -> BridgePolicy:
    return BridgePolicy(allowed_uid=1234, max_duration_hours=168)


def test_peer_uid_must_match_configured_gateway_uid():
    assert authorize_peer(1234, policy()) is True
    assert authorize_peer(0, policy()) is False
    assert authorize_peer(1235, policy()) is False


def test_bridge_rejects_arbitrary_routes():
    with pytest.raises(BridgeRequestError) as exc:
        build_forward_request("POST", "/v1/nft/reconcile", {}, policy())
    assert exc.value.code == "route_not_allowed"


def test_manual_block_forces_source_and_caps_duration():
    method, target, payload = build_forward_request(
        "POST",
        "/v1/decisions/manual",
        {
            "source_id": "attacker",
            "scope": "admin-login",
            "ip": "2001:0db8::1",
            "duration": "24h",
            "reason": "operator request",
            "backend": "application",
        },
        policy(),
    )
    assert method == "POST"
    assert target == "/v1/decisions/manual"
    assert payload["source_id"] == "sg-gateway"
    assert payload["ip"] == "2001:db8::1"

    with pytest.raises(BridgeRequestError) as exc:
        build_forward_request(
            "POST",
            "/v1/decisions/manual",
            {
                "scope": "admin-login",
                "ip": "192.0.2.10",
                "duration": "169h",
                "reason": "too long",
            },
            policy(),
        )
    assert exc.value.code == "invalid_duration"


def test_allowlist_requires_valid_ip_or_cidr():
    method, target, payload = build_forward_request(
        "POST",
        "/v1/allowlist",
        {"prefix": "192.0.2.7/24", "scope": "admin-api", "description": "office"},
        policy(),
    )
    assert method == "POST"
    assert target == "/v1/allowlist"
    assert payload["prefix"] == "192.0.2.0/24"

    with pytest.raises(BridgeRequestError) as exc:
        build_forward_request(
            "POST",
            "/v1/allowlist",
            {"prefix": "not-an-address", "description": "invalid"},
            policy(),
        )
    assert exc.value.code == "invalid_prefix"


def test_bridge_server_is_unix_socket_only():
    assert ManagementUnixServer.address_family == socket.AF_UNIX


class _UpstreamHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):
        return

    def do_GET(self):
        self.server.request_paths.append(self.path)
        payload = json.dumps({"items": []}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(payload)


@contextmanager
def _running(server):
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _unix_http(socket_path, request_bytes):
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        client.settimeout(2)
        client.connect(str(socket_path))
        client.sendall(request_bytes)
        chunks = []
        while True:
            chunk = client.recv(4096)
            if not chunk:
                break
            chunks.append(chunk)
    finally:
        client.close()
    raw = b"".join(chunks)
    header, body = raw.split(b"\r\n\r\n", 1)
    status = int(header.splitlines()[0].split()[1])
    return status, json.loads(body.decode("utf-8"))


def test_bridge_health_uses_real_unix_sockets(tmp_path):
    upstream_path = tmp_path / "upstream.sock"
    bridge_path = tmp_path / "bridge.sock"
    upstream = socketserver.ThreadingUnixStreamServer(str(upstream_path), _UpstreamHandler)
    upstream.daemon_threads = True
    upstream.request_paths = []
    bridge = ManagementUnixServer(
        bridge_path,
        ManagementRequestHandler,
        policy=BridgePolicy(allowed_uid=os.getuid()),
        upstream_socket=upstream_path,
    )

    with _running(upstream), _running(bridge):
        status, payload = _unix_http(
            bridge_path,
            b"GET /v1/health HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n",
        )

    assert status == 200
    assert payload["ok"] is True
    assert upstream.request_paths == ["/v1/decisions?state=active&limit=1"]


def test_bridge_rejects_real_unix_peer_with_wrong_uid(tmp_path):
    bridge_path = tmp_path / "bridge-denied.sock"
    bridge = ManagementUnixServer(
        bridge_path,
        ManagementRequestHandler,
        policy=BridgePolicy(allowed_uid=os.getuid() + 1),
        upstream_socket=tmp_path / "missing-upstream.sock",
    )

    with _running(bridge):
        status, payload = _unix_http(
            bridge_path,
            b"GET /v1/health HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n",
        )

    assert status == 403
    assert payload["code"] == "peer_not_allowed"
