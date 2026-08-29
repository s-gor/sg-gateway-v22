from app.db import connect, init_db


def test_legacy_credentials_are_not_resurrected_after_primary_access_edit(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    init_db()

    with connect() as connection:
        cursor = connection.execute(
            "INSERT INTO clients (name, enabled) VALUES ('Legacy client', 1)"
        )
        client_id = int(cursor.lastrowid)
        connection.execute(
            """
            INSERT INTO client_deployments (
                client_id, engine, status, engine_object_id, config_json
            ) VALUES (?, 'amneziawg', 'applied', 'legacy-key', '{"private_key":"legacy"}')
            """,
            (client_id,),
        )

    init_db()

    with connect() as connection:
        primary = connection.execute(
            "SELECT id FROM devices WHERE client_id = ? AND is_primary = 1",
            (client_id,),
        ).fetchone()
        assert primary is not None
        device_id = int(primary["id"])
        assert connection.execute(
            "SELECT COUNT(*) AS total FROM device_credentials "
            "WHERE device_id = ? AND engine = 'amneziawg'",
            (device_id,),
        ).fetchone()["total"] == 1
        connection.execute(
            "DELETE FROM device_credentials "
            "WHERE device_id = ? AND engine = 'amneziawg'",
            (device_id,),
        )

    # init_db() runs on every request path. A protocol removed by the user must
    # stay removed instead of being copied again from the legacy migration table.
    init_db()

    with connect() as connection:
        assert connection.execute(
            "SELECT COUNT(*) AS total FROM device_credentials "
            "WHERE device_id = ? AND engine = 'amneziawg'",
            (device_id,),
        ).fetchone()["total"] == 0
