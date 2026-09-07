from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

from flask import Flask

from app.db import connect, init_db
from app.naiveproxy import http
from app.naiveproxy.integration import DEFAULT_CONNECTION


ROOT = Path(__file__).parents[1]
HOSTD_RUNTIME_PATH = ROOT / "hostd" / "sg_hostd" / "naiveproxy_runtime.py"
SPEC = importlib.util.spec_from_file_location(
    "naiveproxy_production_runtime_test", HOSTD_RUNTIME_PATH
)
hostd_runtime = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(hostd_runtime)


def test_production_hostd_renderer_disables_caddy_certificate_automation():
    rendered = hostd_runtime._render(
        {
            "domain": "vpn.example.test",
            "port": 8447,
            "certificate_path": "/etc/sg-gateway/naiveproxy/tls/fullchain.pem",
            "private_key_path": "/etc/sg-gateway/naiveproxy/tls/privkey.pem",
        },
        [],
    )

    assert "auto_https off" in rendered
    assert "auto_https disable_redirects" not in rendered


def test_first_failed_apply_restores_unconfigured_database_state(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    init_db()
    with connect() as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO connection_settings (
                engine, enabled, host, port, config_json
            )
            VALUES ('naiveproxy', 1, '', 8447, ?)
            """,
            (DEFAULT_CONNECTION["config_json"],),
        )

    monkeypatch.setattr(
        http,
        "tls_overview",
        lambda: {
            "https_ready": True,
            "domain": "vpn.example.test",
            "certificate_path": "/etc/letsencrypt/live/vpn.example.test/fullchain.pem",
        },
    )
    monkeypatch.setattr(http, "reserved_ports", lambda: {})
    monkeypatch.setattr(
        http,
        "run_hostd_command",
        lambda *args, **kwargs: SimpleNamespace(
            status="error",
            message=(
                "NaiveProxy listener 8447 is not ready after "
                "sg-gateway-naiveproxy.service activation"
            ),
            payload={"service": "sg-gateway-naiveproxy.service"},
        ),
    )

    app = Flask(__name__)
    http.register_naiveproxy_http(app)
    response = app.test_client().post(
        "/api/naiveproxy/settings",
        json={"port": 8447},
    )

    payload = response.get_json()
    restored = http.get_connection_settings("naiveproxy")

    assert response.status_code == 503
    assert payload["settings_rollback"] is True
    assert restored.host == ""
    assert restored.port == 8447
    assert restored.config == {
        "certificate_path": "",
        "country_code": "unknown",
        "domain": "",
        "private_key_path": "",
    }
    assert "Предыдущие настройки в БД восстановлены" in payload["message"]
    assert "Runtime откатился" not in payload["message"]
