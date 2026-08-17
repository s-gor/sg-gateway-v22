from pathlib import Path

from app.main import create_app


def _login(client):
    return client.post("/login", data={"password": "secret"})


def test_system_is_home_and_dashboard_is_removed(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SG_GATEWAY_ADMIN_PASSWORD", "secret")
    client = create_app().test_client()
    _login(client)
    body = client.get("/").get_data(as_text=True)
    assert "SG-GATEWAY / SYSTEM" in body
    assert 'href="/"' in body
    assert "<strong>System</strong>" in body
    assert "Dashboard" not in body
    assert "Оперативная память" in body


def test_flags_are_visible_in_system_shell(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SG_GATEWAY_ADMIN_PASSWORD", "secret")
    client = create_app().test_client()
    _login(client)
    for path in ("/", "/system", "/clients", "/connections", "/routing", "/security"):
        response = client.get(path)
        assert response.status_code == 200
        assert "/static/flags/" in response.get_data(as_text=True)


def test_awg3_uses_the_same_visual_card_contract_as_awg2():
    root = Path(__file__).resolve().parents[1]
    template = (root / "app/web/templates/connections.html").read_text(encoding="utf-8")
    css = (root / "app/web/static/sg-awg-dual-v1.css").read_text(encoding="utf-8")

    assert 'class="awgd-card awgd-card-v2"' in template
    assert 'class="awgd-card awgd-card-v3"' in template
    assert "awgd-runtime-note" not in template
    assert "Отдельный runtime." not in template
    assert ".awgd-card-v3::before" not in css
    assert ".awgd-card-v3 .awgd-generation" not in css
    assert "AWG2/AWG3 symmetric cards: one visual contract" in css
