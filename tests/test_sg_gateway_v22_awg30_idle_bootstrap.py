from __future__ import annotations

from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]


def test_awg30_apply_bootstraps_an_empty_server_runtime() -> None:
    source = (ROOT / "hostd/sg_hostd/awg3_runtime.py").read_text(encoding="utf-8")
    apply_body = source.split("def apply_awg3()", 1)[1]

    # A clean installation has no AWG3 peers yet. That state must still create
    # the independent server key/config and start UDP 586, exactly as AWG31
    # already does. The old early return left the panel forever at
    # "Готов к первому запуску" and deferred server bootstrap to the first
    # client transaction.
    assert "Нет активных клиентов AWG3" not in apply_body
    assert "_ensure_server_secrets()" in apply_body
    assert "_render(rows, secrets)" in apply_body
    assert '["systemctl", "restart", AWG3_SERVICE]' in apply_body


def test_clean_install_checks_awg30_before_creating_any_client() -> None:
    workflow = (ROOT / ".github/workflows/clean-install-awg3-smoke.yml").read_text(
        encoding="utf-8"
    )

    bootstrap_step = "Verify initialized AWG3 before any client"
    create_step = "Create and apply first AWG3 client"
    assert bootstrap_step in workflow
    assert workflow.index(bootstrap_step) < workflow.index(create_step)

    bootstrap = workflow.split(f"- name: {bootstrap_step}", 1)[1]
    bootstrap = bootstrap.split(f"- name: {create_step}", 1)[0]
    assert "systemctl is-active --quiet sg-gateway-awg3.service" in bootstrap
    assert "test -S /run/amneziawg/awg3.sock" in bootstrap
    assert "ip link show dev awg3" in bootstrap
    assert 'awg show awg3 listen-port)" = "586"' in bootstrap
    assert "SG_GATEWAY_AWG3_PUBLIC_KEY" in bootstrap


def test_clean_seed_defers_awg3_until_its_systemd_unit_exists(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from app import install_seed

    settings = {
        "xray": SimpleNamespace(host="", port=443, config={}),
        "amneziawg": SimpleNamespace(host="", port=585, config={}),
        "amneziawg3": SimpleNamespace(host="", port=586, config={}),
        "mihomo": SimpleNamespace(host="", port=2099, config={}),
    }
    environment = {
        "SG_UPDATE_MODE": "0",
        "SG_GATEWAY_DATA_DIR": str(tmp_path),
        "SG_SEED_PUBLIC_ADDRESS": "203.0.113.10",
        "SG_GATEWAY_COUNTRY_CODE": "fr",
        "SG_SEED_VLESS_ENCRYPTION": "mlkem768-test",
        "SG_SEED_XRAY_PUBLIC_KEY": "xray-public-test",
        "SG_SEED_XRAY_SHORT_ID": "0123456789abcdef",
        "SG_SEED_AWG_PUBLIC_KEY": "awg-public-test",
        "SG_SEED_XRAY_PORT": "443",
        "SG_SEED_AWG_PORT": "585",
        "SG_SEED_REALITY_SNI": "www.bing.com",
        "SG_SEED_REALITY_TARGET": "www.bing.com:443",
        "SG_SEED_CREATE_ADMIN": "1",
    }
    for name, value in environment.items():
        monkeypatch.setenv(name, value)

    created: dict[str, str] = {}
    monkeypatch.setattr(install_seed, "init_db", lambda: None)
    monkeypatch.setattr(
        install_seed,
        "get_connection_settings",
        lambda engine: settings[engine],
    )
    monkeypatch.setattr(
        install_seed,
        "update_connection_settings",
        lambda engine, host, port, config: True,
    )
    monkeypatch.setattr(
        install_seed,
        "_synchronize_xray_credentials",
        lambda **kwargs: 0,
    )
    monkeypatch.setattr(install_seed, "count_clients", lambda: 0)

    def capture_client(name: str, requested: str) -> int:
        created["name"] = name
        created["requested"] = requested
        return 1

    monkeypatch.setattr(install_seed, "create_client", capture_client)

    install_seed.seed_or_migrate()

    assert created["name"] == "sg-admin"
    requested = set(created["requested"].split(","))
    assert requested == {
        "xray_reality_tcp",
        "xray_xhttp_reality",
        "amneziawg",
        "mihomo",
        "sgclient",
    }
    assert "amneziawg3" not in requested
    assert "amneziawg31" not in requested
    assert (tmp_path / ".seeded-admin-awg3.pending").read_text(
        encoding="utf-8"
    ).strip() == "sg-admin"


def test_post_runtime_finalizer_adds_only_awg3_and_preserves_existing_access(
    monkeypatch,
) -> None:
    from app.maintenance import seeded_admin_awg3

    row = {"id": 7, "name": "sg-admin", "expires_at": None}

    class FakeConnection:
        def execute(self, query: str, params: tuple[str, ...]):
            assert "FROM clients" in query
            assert params == ("sg-admin",)
            return SimpleNamespace(fetchone=lambda: row)

    monkeypatch.setattr(seeded_admin_awg3, "init_db", lambda: None)
    monkeypatch.setattr(
        seeded_admin_awg3,
        "connect",
        lambda: nullcontext(FakeConnection()),
    )
    monkeypatch.setattr(
        seeded_admin_awg3,
        "get_primary_device",
        lambda client_id: SimpleNamespace(id=19) if client_id == 7 else None,
    )
    existing = [
        "xray_reality_tcp",
        "xray_xhttp_reality",
        "amneziawg",
        "mihomo",
        "sgclient",
    ]
    monkeypatch.setattr(
        seeded_admin_awg3,
        "device_access_tokens",
        lambda device_id: list(existing) if device_id == 19 else [],
    )
    captured: dict[str, object] = {}

    def capture_update(
        client_id: int,
        name: str,
        expires_at: str | None,
        access: str,
    ) -> bool:
        captured.update(
            client_id=client_id,
            name=name,
            expires_at=expires_at,
            access=access,
        )
        return True

    monkeypatch.setattr(seeded_admin_awg3, "update_client", capture_update)

    assert seeded_admin_awg3.ensure_seeded_admin_awg3() is True
    assert captured == {
        "client_id": 7,
        "name": "sg-admin",
        "expires_at": None,
        "access": ",".join(existing + ["amneziawg3"]),
    }
    assert "amneziawg31" not in str(captured["access"])


def test_post_runtime_finalizer_is_idempotent(monkeypatch) -> None:
    from app.maintenance import seeded_admin_awg3

    row = {"id": 7, "name": "sg-admin", "expires_at": None}

    class FakeConnection:
        def execute(self, query: str, params: tuple[str, ...]):
            return SimpleNamespace(fetchone=lambda: row)

    monkeypatch.setattr(seeded_admin_awg3, "init_db", lambda: None)
    monkeypatch.setattr(
        seeded_admin_awg3,
        "connect",
        lambda: nullcontext(FakeConnection()),
    )
    monkeypatch.setattr(
        seeded_admin_awg3,
        "get_primary_device",
        lambda client_id: SimpleNamespace(id=19),
    )
    monkeypatch.setattr(
        seeded_admin_awg3,
        "device_access_tokens",
        lambda device_id: ["amneziawg", "amneziawg3", "sgclient"],
    )
    monkeypatch.setattr(
        seeded_admin_awg3,
        "update_client",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("idempotent finalizer must not rewrite credentials")
        ),
    )

    assert seeded_admin_awg3.ensure_seeded_admin_awg3() is False


def test_update_without_clean_seed_marker_does_not_modify_clients(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from app.maintenance import seeded_admin_awg3

    database = tmp_path / "sg-gateway.sqlite"
    monkeypatch.setattr(
        seeded_admin_awg3,
        "init_db",
        lambda: (_ for _ in ()).throw(
            AssertionError("markerless update must not open or mutate the database")
        ),
    )

    assert seeded_admin_awg3.ensure_seeded_admin_awg3(database=database) is False


def test_stage3a_cli_finalizes_seeded_awg3_before_awg31_migration() -> None:
    installer = (ROOT / "install.sh").read_text(encoding="utf-8")
    stage3a = (ROOT / "app/maintenance/awg31_stage3a.py").read_text(
        encoding="utf-8"
    )

    units = 'run_stage 8 "Создание systemd-служб" stage_systemd_units'
    awg31 = (
        'run_quiet "Этап 10/10 · Подготовка независимого профиля AWG31" '
        "run_awg31_stage3a_migration"
    )
    assert units in installer
    assert awg31 in installer
    assert installer.index(units) < installer.index(awg31)

    finalize = "seeded_awg3_created = ensure_seeded_admin_awg3(database=database)"
    migrate = "result = installer.migrate(database=database)"
    assert finalize in stage3a
    assert migrate in stage3a
    assert stage3a.index(finalize) < stage3a.index(migrate)
