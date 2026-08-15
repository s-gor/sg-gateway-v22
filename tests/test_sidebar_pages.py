from app.main import create_app


def _login(client):
    return client.post("/login", data={"password": "secret"})


def test_sidebar_links_are_english(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SG_GATEWAY_ADMIN_PASSWORD", "secret")
    client = create_app().test_client()
    _login(client)

    response = client.get("/")
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    for href, label in [
        ("/", "System"),
        ("/clients", "Clients"),
        ("/connections", "Connections"),
        ("/outbounds", "Outbounds"),
        ("/routing", "Routing"),
        ("/maintenance", "Maintenance"),
        ("/security", "Security"),
        ("/help", "Help"),
    ]:
        assert f'href="{href}"' in body
        assert f"<strong>{label}</strong>" in body


def test_sidebar_pages_load_real_content(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SG_GATEWAY_ADMIN_PASSWORD", "secret")
    client = create_app().test_client()
    _login(client)
    expectations = {
        "/system": [
            "SG-GATEWAY / SYSTEM",
            "Оперативная память",
            "Проверки состояния",
        ],
        "/clients": [
            "SG-GATEWAY / CLIENTS",
            "Добавить клиента",
            "Клиенты и их устройства",
        ],
        "/connections": [
            "SG-GATEWAY / CONNECTIONS",
            "Xray Server",
            "AmneziaWG",
        ],
        "/outbounds": [
            "SG-GATEWAY / OUTBOUNDS",
            "System outbounds",
            "WARP Outbound",
        ],
        "/routing": [
            "SG-GATEWAY / ROUTING",
            "Выбранная конфигурация",
            "Cloudflare WARP",
        ],
        "/maintenance": [
            "SG-GATEWAY / MAINTENANCE",
            "Последняя копия базы данных",
            "Последние действия",
        ],
        "/security": [
            "SG-GATEWAY / SECURITY",
            "Защищённый доступ к панели",
            "Состояние сертификата",
        ],
        "/help": [
            "SG-GATEWAY / HELP",
            "Справка SG-Gateway",
            "Рабочий маршрут по SG-Gateway",
        ],
    }
    for path, expected_texts in expectations.items():
        response = client.get(path)
        body = response.get_data(as_text=True)

        assert response.status_code == 200
        for text in expected_texts:
            assert text in body
