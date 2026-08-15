from app.clients.repository import create_client
from app.maintenance.service import collect_diagnostics


def test_collect_diagnostics(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    create_client("Samsung", "recommended")

    diagnostics = collect_diagnostics()
    labels = {item.label: item.value for item in diagnostics}

    assert labels["Клиенты"] == "1"
    assert labels["Клиенты AmneziaWG"] == "0"
    assert labels["Клиенты Xray"] == "1"



def test_backup_create_route_shows_feedback(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SG_GATEWAY_ADMIN_PASSWORD", "secret")
    from app.main import create_app

    app = create_app()
    client = app.test_client()
    client.post("/login", data={"password": "secret"})

    response = client.post("/maintenance/backups", follow_redirects=True)
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Резервная копия создана" in body
    assert "sg-gateway-" in body


def test_missing_backup_restore_route_shows_feedback(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SG_GATEWAY_ADMIN_PASSWORD", "secret")
    from app.main import create_app

    app = create_app()
    client = app.test_client()
    client.post("/login", data={"password": "secret"})

    response = client.post("/maintenance/backups/missing.sqlite/restore", follow_redirects=True)
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Резервная копия не найдена" in body



def test_maintenance_page_shows_backup_kind(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SG_GATEWAY_ADMIN_PASSWORD", "secret")
    from app.main import create_app

    app = create_app()
    client = app.test_client()
    client.post("/login", data={"password": "secret"})
    client.post("/maintenance/backups")

    response = client.get("/maintenance")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "ПОСЛЕДНЯЯ КОПИЯ" in body
    assert "Ручная резервная копия" in body
