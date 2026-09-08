from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hostd"))

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
    captured: dict = {}

    def probe(*args, **kwargs):
        captured.update(kwargs)
        return _ProbeResult(
            1,
            stdout='{"ok": false, "error": "xray runtime is not configured"}',
        )

    full = SimpleNamespace(
        _probe=probe,
        _runtime_subprocess_env=lambda: {"EXISTING": "1"},
    )

    result = portable_restore._apply_portable_clients_runtime_required(full)

    assert result is not None
    assert result["ok"] is False
    assert result["deferred"] is True
    assert captured["env"]["EXISTING"] == "1"
    assert captured["env"]["SG_GATEWAY_CLIENTS_KEYS_RESTORE"] == "1"


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


def test_naiveproxy_missing_runtime_is_deferred_only_during_clients_keys_restore(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A restored NaiveProxy credential survives when its destination runtime is absent."""

    from sg_hostd import naiveproxy_client_runtime_patch as naive_patch

    database_path = tmp_path / "sg-gateway.sqlite"
    db = sqlite3.connect(database_path)
    try:
        db.execute("CREATE TABLE connection_settings (engine TEXT, host TEXT)")
        db.execute("CREATE TABLE device_credentials (engine TEXT)")
        db.execute(
            "INSERT INTO connection_settings VALUES ('naiveproxy', 'vpn.example.test')"
        )
        db.execute("INSERT INTO device_credentials VALUES ('naiveproxy')")
        db.commit()
    finally:
        db.close()

    sync_calls: list[str] = []
    runtime = SimpleNamespace(
        DB_PATH=database_path,
        BINARY=tmp_path / "missing-caddy",
        _load=lambda: (
            {"domain": "vpn.example.test", "port": 8447},
            [{"username": "restored-user", "password": "restored-password-123456"}],
            [41],
        ),
        sync=lambda: sync_calls.append("sync") or (_ for _ in ()).throw(
            RuntimeError("NaiveProxy runtime is not installed")
        ),
        _redact=str,
    )
    base = lambda: {"ok": True, "message": "base applied", "engines": []}
    client_runtime = SimpleNamespace(
        apply_all_clients=base,
        ClientRuntimeError=RuntimeError,
    )
    commands = SimpleNamespace(apply_all_clients=base)
    naive_patch.install(client_runtime, commands, runtime)
    monkeypatch.setenv("SG_GATEWAY_CLIENTS_KEYS_RESTORE", "1")

    result = client_runtime.apply_all_clients()

    assert result["ok"] is True
    assert sync_calls == []
    naive = result["engines"][-1]
    assert naive["engine"] == "naiveproxy"
    assert naive["ok"] is False
    assert naive["deferred"] is True
    assert naive["credentials"] == 1


def test_xray_tls_profile_wakes_up_with_same_restored_uuid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Profile readiness may change; the shared restored Xray UUID must not."""

    restored_uuid = "11111111-2222-3333-4444-555555555555"
    client = SimpleNamespace(id=1, name="Restored", enabled=True)
    device = SimpleNamespace(id=7, name="Primary", is_primary=True, enabled=True)
    config = {
        "uuid": restored_uuid,
        "profiles": ["reality_tcp", "xhttp_tls"],
    }
    current = SimpleNamespace(
        enabled=True,
        host="vpn.example.com",
        port=443,
        config={
            "public_key": "server-public-key",
            "short_id": "0123456789abcdef",
            "fingerprint": "firefox",
            "server_name": "www.microsoft.com",
            "vless_encryption": "mlkem768x25519plus.native/xorpub/random.5min.0rtt",
        },
    )
    tls_ready = {"value": False}

    def profile(profile_id: str):
        ready = profile_id == "reality_tcp" or tls_ready["value"]
        port = 443 if profile_id == "xhttp_tls" else 8443
        return (
            {"host": "vpn.example.com", "tls_domain": "vpn.example.com"},
            SimpleNamespace(
                id=profile_id,
                title=profile_id,
                enabled=True,
                ready=ready,
                port=port,
                path="/xhttp",
                mode="auto",
                xmux_enabled=False,
                xmux=None,
            ),
        )

    monkeypatch.setattr(exports, "_deployment_config", lambda *args, **kwargs: config)
    monkeypatch.setattr(exports, "_xray_profile", profile)
    monkeypatch.setattr(exports, "get_connection_settings", lambda engine: current)
    monkeypatch.setattr(exports, "pending_settings_transaction", lambda engine: None)
    monkeypatch.setattr(exports, "_public_export_host", lambda *args: "vpn.example.com")
    monkeypatch.setattr(
        exports,
        "_working_tls_domain",
        lambda: "vpn.example.com" if tls_ready["value"] else "",
    )

    reality = exports.build_xray_profile_link(client, "reality_tcp", device)
    dormant_tls = exports.build_xray_profile_link(client, "xhttp_tls", device)

    assert reality.body
    assert restored_uuid in reality.body
    assert dormant_tls.body == ""

    tls_ready["value"] = True
    awakened_tls = exports.build_xray_profile_link(client, "xhttp_tls", device)

    assert awakened_tls.body
    assert restored_uuid in awakened_tls.body
    assert config["uuid"] == restored_uuid

@pytest.mark.parametrize(
    ("engine", "flag"),
    (("anytls", "anytls_enabled"), ("tuic", "tuic_enabled")),
)
def test_singbox_subprofile_export_readiness_uses_mihomo_connection(
    engine: str,
    flag: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AnyTLS/TUIC readiness comes from Mihomo config, not nonexistent rows."""

    client = SimpleNamespace(id=1, enabled=True)
    device = SimpleNamespace(id=7, enabled=True)
    deployment = SimpleNamespace(status="applied", config_json='{}')
    calls: list[str] = []

    monkeypatch.setattr(exports, "_resolve_device", lambda client, device=None: device)
    monkeypatch.setattr(
        exports,
        "_deployments",
        lambda client, device=None: {engine: deployment},
    )

    def settings(requested_engine: str):
        calls.append(requested_engine)
        if requested_engine != "mihomo":
            raise AssertionError(f"unexpected connection lookup: {requested_engine}")
        return SimpleNamespace(enabled=True, config={flag: True}, host="", port=0)

    monkeypatch.setattr(exports, "get_connection_settings", settings)

    assert exports.is_export_ready(client, engine, device) is True
    assert calls == ["mihomo"]


@pytest.mark.parametrize(
    ("engine", "flag"),
    (("anytls", "anytls_enabled"), ("tuic", "tuic_enabled")),
)
def test_singbox_subprofile_export_stays_dormant_when_profile_flag_is_off(
    engine: str,
    flag: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = SimpleNamespace(id=1, enabled=True)
    device = SimpleNamespace(id=7, enabled=True)
    deployment = SimpleNamespace(status="applied", config_json='{}')

    monkeypatch.setattr(exports, "_resolve_device", lambda client, device=None: device)
    monkeypatch.setattr(
        exports,
        "_deployments",
        lambda client, device=None: {engine: deployment},
    )
    monkeypatch.setattr(
        exports,
        "get_connection_settings",
        lambda requested_engine: SimpleNamespace(
            enabled=True,
            config={flag: False},
            host="",
            port=0,
        ) if requested_engine == "mihomo" else (_ for _ in ()).throw(
            AssertionError(f"unexpected connection lookup: {requested_engine}")
        ),
    )

    assert exports.is_export_ready(client, engine, device) is False



def test_safety_rollback_refreshes_https_before_health_check() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "hostd"
        / "sg_hostd"
        / "clients_keys_portable_restore_patch.py"
    ).read_text(encoding="utf-8")
    rollback = source.split("except Exception as restore_exc:", 1)[1]
    refresh = rollback.index("_refresh_restored_https_from_local_files")
    health = rollback.index("hard._local_panel_health(full)")
    assert refresh < health
