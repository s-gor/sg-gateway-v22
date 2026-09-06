from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.clients import runtime as client_runtime
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


def _prepare_bootstrap(monkeypatch):
    import app.connections.settings as connection_settings
    import app.db as db
    import app.security.tls as tls

    writes: list[tuple[str, int, dict]] = []
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
        lambda engine, host, port, config: writes.append((host, int(port), dict(config))) or True,
    )
    return previous, writes


def test_first_assignment_prepares_https_settings_without_running_hostd(monkeypatch):
    previous, writes = _prepare_bootstrap(monkeypatch)

    result = integration._prepare_runtime_settings()

    assert result is previous
    assert writes == [
        (
            "vpn.example.com",
            8447,
            {
                "domain": "vpn.example.com",
                "certificate_path": "/etc/letsencrypt/live/vpn.example.com/fullchain.pem",
                "private_key_path": "/etc/letsencrypt/live/vpn.example.com/privkey.pem",
            },
        )
    ]


def test_failed_common_client_apply_restores_bootstrap_settings(monkeypatch):
    previous = _previous()
    restored: list[object] = []

    def failed_apply():
        raise client_runtime.ClientWorkflowError("NaiveProxy apply failed")

    monkeypatch.setattr(client_runtime, "apply_clients_runtime", failed_apply)
    monkeypatch.setattr(integration, "_prepare_runtime_settings", lambda: previous)
    monkeypatch.setattr(
        integration,
        "_restore_connection_settings",
        lambda value: restored.append(value) or True,
    )

    integration._patch_client_runtime()

    with pytest.raises(
        client_runtime.ClientWorkflowError,
        match="bootstrap-настройки восстановлены",
    ):
        client_runtime.apply_clients_runtime()

    assert restored == [previous]


def test_successful_common_client_apply_keeps_bootstrap_settings(monkeypatch):
    previous = _previous()
    restored: list[object] = []

    monkeypatch.setattr(
        client_runtime,
        "apply_clients_runtime",
        lambda: {"ok": True, "message": "all runtimes applied"},
    )
    monkeypatch.setattr(integration, "_prepare_runtime_settings", lambda: previous)
    monkeypatch.setattr(
        integration,
        "_restore_connection_settings",
        lambda value: restored.append(value) or True,
    )

    integration._patch_client_runtime()
    result = client_runtime.apply_clients_runtime()

    assert result["ok"] is True
    assert restored == []
