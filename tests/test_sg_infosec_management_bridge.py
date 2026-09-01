import socket

import pytest

from app.security.sg_infosec_bridge import (
    BridgePolicy,
    BridgeRequestError,
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
