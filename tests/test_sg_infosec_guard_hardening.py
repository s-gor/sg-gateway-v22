from __future__ import annotations

from pathlib import Path

from flask import Flask

from app.security.sg_infosec_guard import AlertStore, GuardSettings
from app.security.sg_infosec_guard_runtime import (
    HardenedGuardEngine,
    register_hardened_sg_infosec_guard,
)


class RequestStub:
    path = "/api/status"
    method = "GET"
    query_string = b"id=1%20UNION%20SELECT%20password%20FROM%20users"
    content_type = "text/plain"
    content_length = 0
    endpoint = "api_status"

    def get_data(self, *, cache: bool, as_text: bool = False):
        return "" if as_text else b""


class FailedManagementClient:
    def __init__(self) -> None:
        self.calls = 0

    def create_manual_decision(self, **_payload):
        self.calls += 1
        return False, "bridge unavailable"


class SuccessfulManagementClient:
    def __init__(self) -> None:
        self.calls = 0

    def create_manual_decision(self, **_payload):
        self.calls += 1
        return True, "created"


class RecordingEventClient:
    def __init__(self) -> None:
        self.calls = 0

    def emit_security_event(self, **_payload):
        self.calls += 1
        return True


def test_failed_manual_decision_is_not_marked_as_delivered(tmp_path: Path) -> None:
    management = FailedManagementClient()
    engine = HardenedGuardEngine(
        settings=GuardSettings(mode="enforce"),
        alerts=AlertStore(tmp_path / "alerts.jsonl"),
        management_client=management,
    )
    engine.verify_management_client()

    first = engine.evaluate(RequestStub(), ip="203.0.113.40")
    second = engine.evaluate(RequestStub(), ip="203.0.113.40")

    assert first.action == "block"
    assert second.action == "block"
    assert management.calls == 2
    assert engine._last_block == {}


def test_successful_manual_decision_is_throttled(tmp_path: Path) -> None:
    management = SuccessfulManagementClient()
    engine = HardenedGuardEngine(
        settings=GuardSettings(mode="enforce"),
        alerts=AlertStore(tmp_path / "alerts.jsonl"),
        management_client=management,
    )
    engine.verify_management_client()

    engine.evaluate(RequestStub(), ip="203.0.113.42")
    engine.evaluate(RequestStub(), ip="203.0.113.42")

    assert management.calls == 1
    assert len(engine._last_block) == 1


def test_repeated_findings_are_deduplicated_before_disk_and_event_socket(
    tmp_path: Path,
) -> None:
    event_client = RecordingEventClient()
    engine = HardenedGuardEngine(
        settings=GuardSettings(mode="enforce"),
        alerts=AlertStore(tmp_path / "alerts.jsonl"),
        event_client=event_client,
    )
    engine.verify_event_client()

    decisions = [
        engine.evaluate(RequestStub(), ip="198.51.100.55")
        for _ in range(100)
    ]

    assert all(item.action == "block" for item in decisions)
    assert len({item.alert_id for item in decisions}) == 1
    assert len(engine.alerts.list_recent(500)) == 1
    assert event_client.calls == 1


def test_authenticated_guard_administration_is_not_inspected(tmp_path: Path) -> None:
    app = Flask(__name__)
    app.secret_key = "hardening-test-secret"
    engine = HardenedGuardEngine(
        settings=GuardSettings(mode="enforce"),
        alerts=AlertStore(tmp_path / "alerts.jsonl"),
    )
    register_hardened_sg_infosec_guard(app, engine=engine)

    @app.post("/security/infosec/guard/reputation")
    def reputation_upload():
        return "accepted"

    client = app.test_client()
    with client.session_transaction() as state:
        state["authenticated"] = True

    response = client.post(
        "/security/infosec/guard/reputation",
        data={
            "reputation_json": (
                '{"entries":[],"example":"UNION SELECT password FROM users"}'
            )
        },
        environ_base={"REMOTE_ADDR": "203.0.113.41"},
    )

    assert response.status_code == 200
    assert response.get_data(as_text=True) == "accepted"
    assert engine.alerts.unread_count() == 0
