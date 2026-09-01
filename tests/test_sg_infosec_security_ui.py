from pathlib import Path

from flask import Flask, session

from app.security.sg_infosec_management import register_sg_infosec_management


ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "app" / "web" / "templates"


class FakeManagementClient:
    def __init__(self):
        self.calls = []

    def overview(self):
        return {
            "available": True,
            "status": "Работает",
            "active_decisions": [],
            "active_count": 0,
            "history": [],
            "allowlist": [],
            "allowlist_count": 0,
            "audit": [],
            "last_sync": "now",
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
    app = Flask(__name__, template_folder=str(TEMPLATES))
    app.secret_key = "test-secret"

    @app.context_processor
    def shell_context():
        return {
            "active_page": "security",
            "app_version": "test",
            "is_authenticated": True,
            "server_identity": {
                "address": "127.0.0.1",
                "country_code": "ZZ",
                "country_name": "Test",
                "name": "Test server",
            },
            "country_flag_url": lambda _code: "",
        }

    @app.get("/login")
    def login():
        return "login"

    @app.get("/security")
    def security():
        return "security"

    @app.get("/outbounds")
    def outbounds():
        return "outbounds"

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


def test_context_processor_does_not_probe_bridge_on_unrelated_pages():
    app, management = build_app()
    management.overview = lambda: (_ for _ in ()).throw(AssertionError("unexpected probe"))
    with app.test_request_context("/login"):
        values = {}
        for processor in app.template_context_processors[None]:
            values.update(processor())
    assert "sg_infosec" not in values


def test_registration_ignores_incomplete_production_test_stub():
    class ProductionStub:
        def context_processor(self, func):
            return func

    register_sg_infosec_management(ProductionStub())


def test_partial_has_safe_defaults_and_no_static_endpoint_dependency():
    body = Path("app/web/templates/_sg_infosec_management.html").read_text(encoding="utf-8")
    assert "sg_infosec|default" in body
    assert "url_for('security_infosec_" not in body
    assert 'action="/security/infosec/block"' in body


def test_management_card_is_compact_and_links_complete_guide():
    template = Path(
        "app/web/templates/_sg_infosec_management_base.html"
    ).read_text(encoding="utf-8")
    css = Path("app/web/static/sg-infosec-management-v1.css").read_text(
        encoding="utf-8"
    )

    assert "infosec-card--compact" in template
    assert 'href="/security/infosec/help"' in template
    assert "Полная инструкция" in template
    for contract in (
        ".infosec-card--compact",
        "--infosec-section-gap:12px",
        "--infosec-control-height:38px",
        ".infosec-card--compact .secv2-compact-empty",
        "min-height:0",
        ".infosec-help-layout",
    ):
        assert contract in css


def test_help_page_requires_authentication_and_renders_full_manual():
    app, _ = build_app()
    client = app.test_client()

    anonymous = client.get("/security/infosec/help")
    assert anonymous.status_code in {302, 401}

    authenticate(client)
    response = client.get("/security/infosec/help")
    assert response.status_code == 200
    page = response.get_data(as_text=True)
    for section in (
        "Что защищает SG InfoSec",
        "Автоматическая защита",
        "Ручная блокировка",
        "Allowlist",
        "Веб-защита",
        "Репутация IP",
        "Уведомления",
        "Диагностика",
        "Резервное копирование и откат",
        "Ограничения",
    ):
        assert section in page


def test_repository_manual_covers_operations_and_safety_boundaries():
    guide = Path("docs/SG-INFOSEC-GUIDE-RU.md").read_text(encoding="utf-8")
    for section in (
        "# SG InfoSec: полное руководство",
        "## Что защищает система",
        "## Быстрый старт после установки",
        "## Автоматическая защита SSH",
        "## Защита панели и API",
        "## Веб-защита",
        "## Репутация IP и сетей",
        "## Уведомления",
        "## Ручные блокировки",
        "## Allowlist",
        "## История и аудит",
        "## Резервное копирование и откат",
        "## Диагностика",
        "## Ограничения и модель отказа",
    ):
        assert section in guide
    assert "VPN-порты 585–587" in guide
    assert "fail-open" in guide


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
