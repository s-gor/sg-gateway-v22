from app.connections.settings import get_connection_settings, update_connection_settings
from app.db import init_db


def test_init_db_preserves_gecko_mode(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    init_db()
    settings = get_connection_settings("xray")
    config = dict(settings.config)
    config["hysteria2_obfs_mode"] = "gecko"
    config["hysteria2_obfs_password"] = "G" * 32
    assert update_connection_settings("xray", settings.host or "203.0.113.10", settings.port, config)

    init_db()

    current = get_connection_settings("xray")
    assert current.config["hysteria2_obfs_mode"] == "gecko"
    assert current.config["hysteria2_obfs_password"] == "G" * 32
