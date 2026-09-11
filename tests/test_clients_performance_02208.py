from __future__ import annotations

import sqlite3

from app.clients import repository


class CountingConnection(sqlite3.Connection):
    query_count = 0

    def execute(self, sql, parameters=()):
        if str(sql).lstrip().upper().startswith("SELECT"):
            self.query_count += 1
        return super().execute(sql, parameters)


def test_list_clients_uses_constant_number_of_selects(monkeypatch):
    connection = sqlite3.connect(":memory:", factory=CountingConnection)
    connection.row_factory = sqlite3.Row
    connection.executescript(
        """
        CREATE TABLE clients (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            enabled INTEGER NOT NULL,
            expires_at TEXT
        );
        CREATE TABLE devices (
            id INTEGER PRIMARY KEY,
            client_id INTEGER NOT NULL,
            enabled INTEGER NOT NULL
        );
        CREATE TABLE device_credentials (
            id INTEGER PRIMARY KEY,
            device_id INTEGER NOT NULL,
            engine TEXT NOT NULL,
            status TEXT NOT NULL
        );
        """
    )
    for client_id in range(1, 26):
        connection.execute(
            "INSERT INTO clients(id, name, enabled, expires_at) VALUES (?, ?, 1, NULL)",
            (client_id, f"client-{client_id}"),
        )
        connection.execute(
            "INSERT INTO devices(id, client_id, enabled) VALUES (?, ?, 1)",
            (client_id, client_id),
        )
        connection.execute(
            "INSERT INTO device_credentials(id, device_id, engine, status) VALUES (?, ?, 'xray', 'applied')",
            (client_id, client_id),
        )
    connection.commit()
    connection.query_count = 0

    monkeypatch.setattr(repository, "init_db", lambda: None)
    monkeypatch.setattr(repository, "connect", lambda: connection)

    clients = repository.list_clients()

    assert len(clients) == 25
    assert clients[0].id == 25
    assert clients[-1].id == 1
    assert all(client.device_count == 1 for client in clients)
    assert all(client.active_device_count == 1 for client in clients)
    assert all(client.xray_status == "applied" for client in clients)
    assert connection.query_count == 3
