import sqlite3
from types import SimpleNamespace


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


def test_list_connections_reuses_preloaded_settings(monkeypatch):
    from app.connections import service

    db = sqlite3.connect(':memory:')
    db.row_factory = sqlite3.Row
    db.execute('CREATE TABLE device_credentials (engine TEXT)')
    db.commit()

    settings_map = {
        'xray': SimpleNamespace(enabled=True, host='127.0.0.1', port=443, config={'country_code': 'fr'}),
        'mihomo': SimpleNamespace(enabled=True, host='127.0.0.1', port=2099, config={'country_code': 'fr'}),
        'amneziawg31': SimpleNamespace(enabled=True, host='127.0.0.1', port=587, config={'country_code': 'fr'}),
    }

    monkeypatch.setattr(service, 'connect', lambda: db)
    monkeypatch.setattr(
        service,
        'list_connection_settings',
        lambda *_: (_ for _ in ()).throw(AssertionError('preloaded settings must be reused')),
    )

    result = service.list_connections(settings_map=settings_map)

    assert [item.name for item in result] == ['amneziawg31', 'xray', 'mihomo']
