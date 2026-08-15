from app.main import create_app


def test_dashboard_requires_login(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SG_GATEWAY_ADMIN_PASSWORD", "secret")
    app = create_app()
    client = app.test_client()

    response = client.get("/")

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_login_allows_dashboard(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SG_GATEWAY_ADMIN_PASSWORD", "secret")
    app = create_app()
    client = app.test_client()

    response = client.post("/login", data={"password": "secret"}, follow_redirects=True)
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "SG-Gateway" in body
    assert "SG-GATEWAY / SYSTEM" in body
    assert "<h1>System</h1>" in body
    assert "Оперативная память" in body
    assert "Проверки состояния" in body
    assert 'href="/clients"' in body


def test_recovery_stays_public(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    app = create_app()
    client = app.test_client()

    response = client.get("/recovery")

    assert response.status_code == 200



def test_invalid_client_name_shows_feedback(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SG_GATEWAY_ADMIN_PASSWORD", "secret")
    app = create_app()
    client = app.test_client()
    client.post("/login", data={"password": "secret"})

    response = client.post("/clients", data={"name": "   ", "access": "recommended"}, follow_redirects=True)
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Клиент не создан" in body
    assert "Имя должно быть уникальным" in body
    assert "минимум один протокол" in body



def test_missing_client_action_returns_404(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SG_GATEWAY_ADMIN_PASSWORD", "secret")
    app = create_app()
    client = app.test_client()
    client.post("/login", data={"password": "secret"})

    response = client.post("/clients/404/disable")

    assert response.status_code == 404
