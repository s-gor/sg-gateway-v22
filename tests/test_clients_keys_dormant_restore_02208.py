from __future__ import annotations

import sqlite3
from types import SimpleNamespace

import pytest

from app.clients import exports
from sg_hostd import clients_keys_portable_restore_patch as portable_restore


class _ProbeResult:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_portable_restore_runtime_reconcile_is_nonfatal_when_destination_runtime_is_not_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Durable Clients & Keys restore must survive transient runtime unavailability."""

    monkeypatch.setattr(portable_restore.Path, "is_file", lambda self: True)
    full = SimpleNamespace(
        _probe=lambda *args, **kwargs: _ProbeResult(
            1,
            stdout='{"ok": false, "error": "xray runtime is not configured"}',
        ),
        _runtime_subprocess_env=lambda: {},
    )

    result = portable_restore._apply_portable_clients_runtime_required(full)

    assert result is not None
    assert result["ok"] is False
    assert result["deferred"] is True


def test_applied_xray_credential_is_not_export_ready_when_connection_is_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Credential entitlement and current server readiness are separate states."""

    client = SimpleNamespace(id=1, enabled=True)
    device = SimpleNamespace(id=7, enabled=True)
    deployment = SimpleNamespace(
        status="applied",
        config_json='{"uuid":"restored-uuid","profiles":["reality_tcp","xhttp_tls"]}',
    )

    monkeypatch.setattr(exports, "_resolve_device", lambda client, device=None: device)
    monkeypatch.setattr(
        exports,
        "_deployments",
        lambda client, device=None: {"xray": deployment},
    )
    monkeypatch.setattr(
        exports,
        "get_connection_settings",
        lambda engine: SimpleNamespace(enabled=False, config={}, host="", port=0),
    )

    assert exports.is_export_ready(client, "xray", device) is False


def test_destination_runtime_policy_hides_only_unready_engine_and_restores_credential(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One missing runtime must not block ready restored protocols."""

    database_path = tmp_path / "sg-gateway.sqlite"
    db = sqlite3.connect(database_path)
    try:
        db.execute(
            "CREATE TABLE device_credentials (id INTEGER PRIMARY KEY, engine TEXT, status TEXT)"
        )
        db.executemany(
            "INSERT INTO device_credentials(id, engine, status) VALUES (?, ?, ?)",
            [
                (1, "amneziawg", "applied"),
                (2, "xray", "applied"),
            ],
        )
        db.commit()
    finally:
        db.close()

    from sg_hostd import runtime_contracts

    monkeypatch.setattr(
        runtime_contracts,
        "inspect_runtime_contract",
        lambda **kwargs: {
            "ok": False,
            "failures": [{"engine": "xray", "ready": False}],
            "checks": [
                {"engine": "amneziawg", "ready": True},
                {"engine": "xray", "ready": False},
            ],
        },
    )

    with portable_restore._destination_runtime_policy(database_path) as state:
        db = sqlite3.connect(database_path)
        try:
            statuses = dict(db.execute("SELECT engine, status FROM device_credentials"))
        finally:
            db.close()
        assert state["deferred_engines"] == ["xray"]
        assert statuses["amneziawg"] == "applied"
        assert statuses["xray"] == "disabled"

    db = sqlite3.connect(database_path)
    try:
        statuses = dict(db.execute("SELECT engine, status FROM device_credentials"))
    finally:
        db.close()
    assert statuses == {"amneziawg": "applied", "xray": "applied"}
