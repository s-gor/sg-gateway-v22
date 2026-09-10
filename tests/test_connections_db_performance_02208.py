import sqlite3


def test_connection_settings_batch_uses_one_database_read(monkeypatch):
    from app.connections import settings

    db = sqlite3.connect(':memory:')
    db.row_factory = sqlite3.Row
    db.execute('CREATE TABLE connection_settings (engine TEXT PRIMARY KEY, enabled INTEGER, host TEXT, port INTEGER, config_json TEXT)')
    for engine, port in [('xray', 443), ('mihomo', 2099), ('amneziawg31', 587)]:
        db.execute(
            'INSERT INTO connection_settings(engine, enabled, host, port, config_json) VALUES (?, 1, ?, ?, ?)',
            (engine, f'{engine}.example', port, '{}'),
        )
    db.commit()
    calls = 0

    def fake_connect():
        nonlocal calls
        calls += 1
        return db

    monkeypatch.setattr(settings, 'connect', fake_connect)
    result = settings.list_connection_settings(('xray', 'mihomo', 'amneziawg31'))
    assert set(result) == {'xray', 'mihomo', 'amneziawg31'}
    assert result['xray'].port == 443
    assert calls == 1
