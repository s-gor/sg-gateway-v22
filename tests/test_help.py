from app.help.content import get_topic, list_topics
from app.main import create_app


def _login(client):
    return client.post("/login", data={"password": "secret"})


def test_help_topics_exist():
    topics = list_topics()

    assert get_topic("clients") is not None
    assert len(topics) >= 5


def test_help_page_loads(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SG_GATEWAY_ADMIN_PASSWORD", "secret")
    client = create_app().test_client()
    _login(client)

    response = client.get("/help")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "SG-Gateway" in body
    assert 'href="/help/clients"' in body


def test_help_topic_loads(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SG_GATEWAY_ADMIN_PASSWORD", "secret")
    client = create_app().test_client()
    _login(client)

    response = client.get("/help/clients")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "SG-Gateway" in body
    assert 'href="/help/clients"' in body