from __future__ import annotations

from pathlib import Path

import pytest

from app.clients.repository import get_client
from app.clients import sg_subscription_store as store
from app.db import connect, init_db


@pytest.fixture()
def isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    data_dir = tmp_path / "data"
    monkeypatch.setenv("SG_GATEWAY_DATA_DIR", str(data_dir))
    monkeypatch.setenv("SG_GATEWAY_PUBLIC_ADDRESS", "198.51.100.10")
    monkeypatch.setenv("SG_GATEWAY_PUBLIC_PORT", "8080")
    init_db()
    return data_dir / "sg-gateway.sqlite"


def _insert_client(*, sgclient: bool) -> int:
    with connect() as connection:
        cursor = connection.execute(
            "INSERT INTO clients (name, enabled) VALUES ('Subscription test', 1)"
        )
        client_id = int(cursor.lastrowid)
        device = connection.execute(
            "INSERT INTO devices (client_id, name, enabled, is_primary) VALUES (?, 'Primary', 1, 1)",
            (client_id,),
        )
        if sgclient:
            connection.execute(
                "INSERT INTO device_credentials (device_id, engine, status, config_json) VALUES (?, 'sgclient', 'applied', '{}')",
                (int(device.lastrowid),),
            )
    return client_id


def test_token_is_created_only_for_client_with_sgclient(isolated_db: Path) -> None:
    no_sgclient = _insert_client(sgclient=False)
    with_sgclient = _insert_client(sgclient=True)

    assert store.ensure_client_subscription_token(999999) == ""
    assert store.ensure_client_subscription_token(no_sgclient) == ""

    token = store.ensure_client_subscription_token(with_sgclient)
    assert token.startswith("sg1_")
    assert len(token) >= 32
    assert store.ensure_client_subscription_token(with_sgclient) == token

    with connect() as connection:
        row = connection.execute(
            "SELECT token FROM sg_subscription_tokens WHERE client_id = ?",
            (with_sgclient,),
        ).fetchone()
    assert row is not None
    assert str(row["token"]) == token


def test_token_resolves_back_to_client_and_rejects_invalid_values(isolated_db: Path) -> None:
    client_id = _insert_client(sgclient=True)
    token = store.ensure_client_subscription_token(client_id)

    client = store.get_client_by_subscription_token(token)
    assert client is not None
    assert client.id == client_id
    assert store.get_client_by_subscription_token("") is None
    assert store.get_client_by_subscription_token("sg1_short") is None
    assert store.get_client_by_subscription_token("x" * 300) is None


def test_subscription_url_prefers_ready_https_public_url(
    isolated_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client_id = _insert_client(sgclient=True)
    client = get_client(client_id)
    assert client is not None
    monkeypatch.setattr(
        store,
        "tls_overview",
        lambda: {
            "https_ready": True,
            "public_url": "https://gateway.example.test/",
        },
    )

    url = store.build_sg_subscription_url(client)
    assert url.startswith("https://gateway.example.test/sg/sub/v1/sg1_")


def test_subscription_url_falls_back_to_configured_public_address(
    isolated_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client_id = _insert_client(sgclient=True)
    client = get_client(client_id)
    assert client is not None
    monkeypatch.setattr(
        store,
        "tls_overview",
        lambda: {"https_ready": False, "public_url": ""},
    )

    url = store.build_sg_subscription_url(client)
    assert url.startswith("http://198.51.100.10:8080/sg/sub/v1/sg1_")
