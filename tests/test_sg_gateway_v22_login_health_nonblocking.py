from flask import Flask

from app.maintenance import health as health_module


def test_login_health_summary_skips_full_runtime_checks(monkeypatch):
    app = Flask(__name__)

    @app.get("/login", endpoint="login")
    def login_route():
        return health_module.health_summary()

    def unexpected_full_health():
        raise AssertionError("login must not run full runtime health checks")

    monkeypatch.setattr(health_module, "collect_health_checks", unexpected_full_health)

    with app.test_client() as client:
        response = client.get("/login")

    assert response.status_code == 200
    assert response.get_data(as_text=True) == "ok"


def test_health_summary_still_uses_full_checks_outside_login(monkeypatch):
    monkeypatch.setattr(
        health_module,
        "collect_health_checks",
        lambda: [health_module.HealthCheck("test", "warning", "test")],
    )

    assert health_module.health_summary() == "warning"
