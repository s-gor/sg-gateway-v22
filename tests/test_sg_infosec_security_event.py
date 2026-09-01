from __future__ import annotations

import json
from pathlib import Path

from app.security.sg_infosec import SGInfoSecClient, build_security_event


def test_structured_security_event_keeps_only_safe_metadata() -> None:
    event = build_security_event(
        scope="admin-api",
        ip="203.0.113.9",
        route="api.client.create",
        metadata={
            "reason": "web-threat",
            "score": 95.0,
            "rule_ids": ["sqli", "reputation"],
            "country": "ZZ",
            "asn": 64500.0,
        },
    )

    assert event["event_type"] == "api.auth_failed"
    assert event["scope"] == "admin-api"
    assert event["metadata"]["route"] == "api.client.create"
    assert event["metadata"]["rule_ids"] == ["sqli", "reputation"]
    serialized = json.dumps(event).lower()
    for forbidden in ("password", "cookie", "authorization", "private_key"):
        assert forbidden not in serialized


def test_structured_security_event_rejects_sensitive_metadata() -> None:
    try:
        build_security_event(
            scope="admin-api",
            ip="203.0.113.9",
            route="api.client.create",
            metadata={"token": "secret"},
        )
    except ValueError as exc:
        assert "sensitive" in str(exc)
    else:
        raise AssertionError("sensitive metadata was accepted")


def test_client_emits_structured_event_through_events_socket(tmp_path: Path) -> None:
    captured = []

    class RecordingClient(SGInfoSecClient):
        def _post_json(self, socket_path, target, payload):
            captured.append((socket_path, target, payload))
            return 202, {"accepted": True}

    client = RecordingClient(
        control_socket=tmp_path / "control.sock",
        events_socket=tmp_path / "events.sock",
    )

    assert client.emit_security_event(
        scope="admin-api",
        ip="203.0.113.10",
        route="api.status",
        metadata={"reason": "web-threat", "score": 90.0},
    )
    assert captured[0][0] == tmp_path / "events.sock"
    assert captured[0][1] == "/v1/events"
    assert captured[0][2]["metadata"]["score"] == 90.0
