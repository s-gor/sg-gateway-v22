from flask import Flask, session

from app.security.sg_infosec_management import register_sg_infosec_management


class FakeManagementClient:
    def __init__(self):
        self.calls = []

    def overview(self):
        return {
            "available": True,
            "status": "Работает",
            "active_decisions": [],
            "active_count": 0,
            "allowlist": [],
            "allowlist_count": 0,
            "audit": [],
            "error": "",
        }

    def create_manual_decision(self, **payload):
        self.calls.append(("block", payload))
        return True, "IP заблокирован"

    def revoke_decision(self, decision_id):
        self.calls.append(("revoke", decision_id))
        return True, "Блокировка снята"

    def create_allowlist(self, **payload):
        self.calls.append(("allowlist", payload))
        return True, "Allowlist обновлён"

    def delete_allowlist(self, entry_id):
        self.calls.append(("allowlist-delete", entry_id))
        return True, "Allowlist обновлён"


def build_app():
    app = Flask(__name__)
    app.secret_key = "test-secret"

    @app.get("/login")
    def login():
        return "login"

    @app.get("/security")
    def security():
        return "security"

    client = FakeManagementClient()
    register_sg_infosec_management(app, client=client)
    return app, client


def authenticate(client):
    with client.session_transaction() as state:
        state["authenticated"] = True
        state["sg_infosec_csrf"] = "known-token"


def test_context_processor_exposes_overview_and_csrf_token():
    app, _ = build_app()
    with app.test_request_context("/security"):
        session["authenticated"] = True
        values = {}
        for processor in app.template_context_processors[None]:
            values.update(processor())
    assert values["sg_infosec"]["available"] is True
    assert values["sg_infosec_csrf_token"]


def test_mutation_requires_authenticated_session():
    app, _ = build_app()
    response = app.test_client().post(
        "/security/infosec/block",
        data={"csrf_token": "x", "ip": "192.0.2.1", "scope": "admin-login", "hours": "1", "reason": "test"},
    )
    assert response.status_code in {302, 401}


def test_mutation_rejects_missing_csrf():
    app, _ = build_app()
    client = app.test_client()
    authenticate(client)
    response = client.post(
        "/security/infosec/block",
        data={"ip": "192.0.2.1", "scope": "admin-login", "hours": "1", "reason": "test"},
    )
    assert response.status_code == 400


def test_manual_block_is_validated_and_forwarded():
    app, management = build_app()
    client = app.test_client()
    authenticate(client)
    response = client.post(
        "/security/infosec/block",
        data={
            "csrf_token": "known-token",
            "ip": "192.0.2.1",
            "scope": "admin-login",
            "hours": "24",
            "reason": "operator request",
        },
    )
    assert response.status_code == 302
    assert management.calls == [
        (
            "block",
            {
                "ip": "192.0.2.1",
                "scope": "admin-login",
                "duration": "24h",
                "reason": "operator request",
            },
        )
    ]


def test_mutation_routes_are_post_only():
    app, _ = build_app()
    response = app.test_client().get("/security/infosec/block")
    assert response.status_code == 405
