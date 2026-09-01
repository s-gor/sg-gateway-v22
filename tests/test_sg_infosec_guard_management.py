from __future__ import annotations

import json
from pathlib import Path

from flask import Flask, session

from app.security.sg_infosec_guard import AlertStore, GuardEngine, GuardSettings
from app.security.sg_infosec_guard_management import (
    register_sg_infosec_guard_management,
)


def build_app(tmp_path: Path):
    app = Flask(__name__)
    app.secret_key = "guard-test-secret"

    @app.get("/login")
    def login():
        return "login"

    @app.get("/security")
    def security():
        return "security"

    engine = GuardEngine(
        settings=GuardSettings(mode="monitor"),
        alerts=AlertStore(tmp_path / "alerts.jsonl"),
    )
    app.extensions["sg_infosec_guard"] = {"engine": engine}
    register_sg_infosec_guard_management(app)
    return app, engine


def authenticate(client) -> None:
    with client.session_transaction() as state:
        state["authenticated"] = True
        state["sg_infosec_csrf"] = "known-token"


def test_guard_context_is_scoped_to_authenticated_security_page(tmp_path: Path) -> None:
    app, engine = build_app(tmp_path)
    engine.alerts.append(
        ip="203.0.113.1",
        action="monitor",
        score=50,
        rule_ids=["test"],
        scope="admin-api",
        reputation={},
    )
    with app.test_request_context("/security"):
        session["authenticated"] = True
        values = {}
        for processor in app.template_context_processors[None]:
            values.update(processor())
    assert values["sg_infosec_guard"]["unread_count"] == 1

    with app.test_request_context("/login"):
        session["authenticated"] = True
        values = {}
        for processor in app.template_context_processors[None]:
            values.update(processor())
    assert "sg_infosec_guard" not in values


def test_settings_route_validates_persists_and_updates_engine(
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings_path = tmp_path / "guard.json"
    monkeypatch.setenv("SG_INFOSEC_GUARD_SETTINGS", str(settings_path))
    app, engine = build_app(tmp_path)
    client = app.test_client()
    authenticate(client)

    response = client.post(
        "/security/infosec/guard/settings",
        data={
            "csrf_token": "known-token",
            "mode": "enforce",
            "max_body_bytes": "32768",
            "login_requests_per_minute": "12",
            "api_requests_per_minute": "90",
            "block_score": "85",
            "notification_min_score": "75",
            "notification_webhook": "https://example.invalid/hook",
        },
    )

    assert response.status_code == 302
    assert engine.settings.mode == "enforce"
    assert engine.settings.block_score == 85
    persisted = json.loads(settings_path.read_text(encoding="utf-8"))
    assert persisted["max_body_bytes"] == 32768


def test_reputation_route_validates_atomically_and_reloads(
    tmp_path: Path,
    monkeypatch,
) -> None:
    reputation_path = tmp_path / "reputation.json"
    monkeypatch.setenv("SG_INFOSEC_REPUTATION_FILE", str(reputation_path))
    app, engine = build_app(tmp_path)
    client = app.test_client()
    authenticate(client)

    response = client.post(
        "/security/infosec/guard/reputation",
        data={
            "csrf_token": "known-token",
            "reputation_json": json.dumps(
                {
                    "entries": [
                        {
                            "cidr": "203.0.113.0/24",
                            "score": 91,
                            "country": "ZZ",
                            "asn": 64500,
                            "tags": ["scanner"],
                        }
                    ]
                }
            ),
        },
    )

    assert response.status_code == 302
    assert reputation_path.exists()
    assert engine.reputation.lookup("203.0.113.9").score == 91


def test_alert_ack_routes_require_csrf_and_update_store(tmp_path: Path) -> None:
    app, engine = build_app(tmp_path)
    identifier = engine.alerts.append(
        ip="198.51.100.7",
        action="block",
        score=95,
        rule_ids=["sqli"],
        scope="admin-api",
        reputation={},
    )
    client = app.test_client()
    authenticate(client)

    rejected = client.post(
        f"/security/infosec/guard/alerts/{identifier}/ack",
        data={},
    )
    assert rejected.status_code == 400

    accepted = client.post(
        f"/security/infosec/guard/alerts/{identifier}/ack",
        data={"csrf_token": "known-token"},
    )
    assert accepted.status_code == 302
    assert engine.alerts.unread_count() == 0


def test_guard_template_exposes_policy_alerts_and_reputation_controls() -> None:
    body = Path("app/web/templates/_sg_infosec_guard.html").read_text(
        encoding="utf-8"
    )
    assert "/security/infosec/guard/settings" in body
    assert "/security/infosec/guard/reputation" in body
    assert "/security/infosec/guard/alerts/ack-all" in body
    assert "notification_webhook" in body
    assert "reputation_json" in body
