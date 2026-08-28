from __future__ import annotations

import json
from pathlib import Path

import pytest

from app import db


ROOT = Path(__file__).resolve().parents[1]
AWG_ENGINES = ("amneziawg", "amneziawg3", "amneziawg31")


@pytest.fixture()
def isolated_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    database = tmp_path / "sg-gateway.sqlite"
    monkeypatch.setattr(db, "get_database_path", lambda: database)
    db.init_db()
    return database


def _seed_credentials() -> None:
    with db.connect() as connection:
        client_id = int(
            connection.execute(
                "INSERT INTO clients (name, enabled) VALUES ('DNS Contract', 1)"
            ).lastrowid
        )
        device_id = int(
            connection.execute(
                """
                INSERT INTO devices (client_id, name, enabled, is_primary)
                VALUES (?, 'Основной доступ', 1, 1)
                """,
                (client_id,),
            ).lastrowid
        )
        for engine in AWG_ENGINES:
            payload = {
                "private_key": f"{engine}-private",
                "server_public_key": f"{engine}-server",
                "dns": "1.1.1.1",
            }
            connection.execute(
                """
                INSERT INTO device_credentials
                    (device_id, engine, status, engine_object_id, config_json)
                VALUES (?, ?, 'applied', ?, ?)
                """,
                (
                    device_id,
                    engine,
                    f"{engine}-object",
                    json.dumps(payload, sort_keys=True),
                ),
            )


def _settings_dns() -> dict[str, str]:
    with db.connect() as connection:
        rows = connection.execute(
            "SELECT engine, config_json FROM connection_settings "
            "WHERE engine IN ('amneziawg', 'amneziawg3', 'amneziawg31')"
        ).fetchall()
    return {
        str(row["engine"]): str(json.loads(row["config_json"])["dns"])
        for row in rows
    }


def _credential_payloads() -> dict[str, tuple[str, dict]]:
    with db.connect() as connection:
        rows = connection.execute(
            "SELECT engine, status, config_json FROM device_credentials"
        ).fetchall()
    return {
        str(row["engine"]): (str(row["status"]), json.loads(row["config_json"]))
        for row in rows
    }


def _authenticated_client():
    from app.main import create_app

    app = create_app()
    client = app.test_client()
    with client.session_transaction() as session:
        session["authenticated"] = True
    return client


def test_shared_awg_dns_updates_all_settings_and_existing_credentials(
    isolated_database: Path,
) -> None:
    from app.connections.awg_dns import get_shared_awg_dns, set_shared_awg_dns

    _seed_credentials()

    state = set_shared_awg_dns("9.9.9.9")

    assert state.dns == "9.9.9.9"
    assert state.consistent is True
    assert _settings_dns() == {engine: "9.9.9.9" for engine in AWG_ENGINES}

    credentials = _credential_payloads()
    assert set(credentials) == set(AWG_ENGINES)
    for engine, (status, payload) in credentials.items():
        assert status == "applied"
        assert payload["dns"] == "9.9.9.9"
        assert payload["private_key"] == f"{engine}-private"
        assert payload["server_public_key"] == f"{engine}-server"

    assert get_shared_awg_dns().dns == "9.9.9.9"


def test_shared_awg_dns_rejects_invalid_value_without_partial_update(
    isolated_database: Path,
) -> None:
    from app.connections.awg_dns import SharedAwgDnsError, set_shared_awg_dns

    _seed_credentials()
    before_settings = _settings_dns()
    before_credentials = _credential_payloads()

    with pytest.raises(SharedAwgDnsError):
        set_shared_awg_dns("not-a-dns-server")

    assert _settings_dns() == before_settings
    assert _credential_payloads() == before_credentials


def test_awg31_parameter_save_preserves_shared_dns(isolated_database: Path) -> None:
    from app.connections.awg31 import get_settings, save_settings
    from app.connections.awg_dns import set_shared_awg_dns

    set_shared_awg_dns("8.8.8.8")
    current = get_settings()
    save_settings(current.parameters)

    assert get_settings().dns == "8.8.8.8"
    assert _settings_dns()["amneziawg31"] == "8.8.8.8"


def test_connections_has_one_visible_shared_dns_form_and_compact_card_lines() -> None:
    connections = (ROOT / "app/web/templates/connections.html").read_text(encoding="utf-8")
    awg31 = (ROOT / "app/web/templates/_awg31_panel.html").read_text(encoding="utf-8")

    assert connections.count('action="{{ url_for(\'update_awg_dns\') }}"') == 1
    assert connections.count('name="dns"') == 1
    assert awg31.count('name="dns"') == 0
    assert 'class="awgd-shared-dns' in connections
    assert "DNS клиентов AWG" in connections
    assert "Используется устройствами при активном VPN" in connections

    assert "{{ awg_public_host }}:{{ awg_settings.port }} · DNS {{ awg_dns.dns }}" in connections
    assert "{{ awg3_public_host }}:{{ awg3_settings.port }} · DNS {{ awg_dns.dns }}" in connections
    assert "{{ awg31_public_host }}:587 · DNS {{ awg_dns.dns }}" in awg31

    assert connections.count('class="cnv1-engine-form cnv1-engine-form-compact awgd-legacy-settings" hidden') == 2
    assert 'class="cnv1-engine-form cnv1-engine-form-compact awgd-v31-form" hidden' in awg31


def test_shared_dns_form_route_updates_all_awg_profiles(isolated_database: Path) -> None:
    client = _authenticated_client()

    response = client.post("/connections/awg-dns", data={"dns": "8.8.4.4"})

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/connections#awg-dns")
    assert _settings_dns() == {engine: "8.8.4.4" for engine in AWG_ENGINES}


def test_legacy_profile_forms_cannot_diverge_the_shared_dns(
    isolated_database: Path,
) -> None:
    from app.connections.awg_dns import set_shared_awg_dns

    set_shared_awg_dns("9.9.9.9")
    client = _authenticated_client()

    response = client.post(
        "/connections/amneziawg",
        data={
            "host": "vpn.example",
            "port": "585",
            "dns": "8.8.8.8",
            "country_code": "nl",
            "server_public_key": "awg2-server",
        },
    )
    assert response.status_code == 302

    response = client.post(
        "/connections/amneziawg3",
        data={
            "host": "vpn.example",
            "port": "586",
            "dns": "8.8.4.4",
            "server_public_key": "awg3-server",
        },
    )
    assert response.status_code == 302

    assert _settings_dns() == {engine: "9.9.9.9" for engine in AWG_ENGINES}
