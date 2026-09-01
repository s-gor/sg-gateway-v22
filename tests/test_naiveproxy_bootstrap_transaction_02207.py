from __future__ import annotations

from types import SimpleNamespace

from app.naiveproxy import integration


class _Connection:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query):
        if "SELECT host" in query:
            return _Result({"host": ""})
        if "COUNT(*)" in query:
            return _Result({"total": 1})
        raise AssertionError(query)


class _Result:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


def _previous():
    return SimpleNamespace(
        host="",
        port=8447,
        config={
            "domain": "",
            "certificate_path": "",
            "private_key_path": "",
            "country_code": "unknown",
        },
    )


def _prepare(monkeypatch, *, hostd_status: str):
    import app.connections.settings as connection_settings
    import app.db as db
    import app.hostd.client as hostd_client
    import app.maintenance.operations as operations
    import app.security.tls as tls

    writes: list[tuple[str, int, dict]] = []
    logs: list[dict] = []
    previous = _previous()
    monkeypatch.setattr(db, "connect", lambda: _Connection())
    monkeypatch.setattr(
        tls,
        "overview",
        lambda: {
            "https_ready": True,
            "domain": "vpn.example.com",
            "certificate_path": "/etc/letsencrypt/live/vpn.example.com/fullchain.pem",
        },
    )
    monkeypatch.setattr(
        connection_settings,
        "get_connection_settings",
        lambda engine: previous,
    )
    monkeypatch.setattr(
        connection_settings,
        "update_connection_settings",
        lambda engine, host, port, config: writes.append((host, port, config)) or True,
    )
    monkeypatch.setattr(
        hostd_client,
        "run_hostd_command",
        lambda *args, **kwargs: SimpleNamespace(
            status=hostd_status,
            message="runtime failed" if hostd_status != "ok" else "runtime applied",
            payload={},
        ),
    )
    monkeypatch.setattr(
        operations,
        "log_operation",
        lambda action, target, message, status="ok": logs.append(
            {
                "action": action,
                "target": target,
                "message": message,
                "status": status,
            }
        ),
    )
    return previous, writes, logs


def test_failed_first_bootstrap_restores_blank_connection_settings(monkeypatch):
    previous, writes, logs = _prepare(monkeypatch, hostd_status="error")

    integration._request_sync()

    assert writes[0][0:2] == ("vpn.example.com", 8447)
    assert writes[1] == (previous.host, previous.port, previous.config)
    assert logs[-1]["status"] == "error"
    assert "bootstrap-настройки восстановлены" in logs[-1]["message"]


def test_successful_first_bootstrap_keeps_applied_connection_settings(monkeypatch):
    _previous_settings, writes, logs = _prepare(monkeypatch, hostd_status="ok")

    integration._request_sync()

    assert len(writes) == 1
    assert writes[0][0:2] == ("vpn.example.com", 8447)
    assert logs == []
