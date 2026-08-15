from app.main import create_app


def test_recovery_page_loads(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    client = create_app().test_client()

    response = client.get("/recovery")

    assert response.status_code == 200
    assert "SG-Gateway Recovery" in response.get_data(as_text=True)