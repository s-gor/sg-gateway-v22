from sg_hostd.app import create_app


def test_health_endpoint():
    client = create_app().test_client()

    response = client.get("/health")

    assert response.status_code == 200
    assert response.get_json()["service"] == "sg-hostd"


def test_unknown_command_returns_403():
    client = create_app().test_client()

    response = client.post("/commands/shell.rm")

    assert response.status_code == 403