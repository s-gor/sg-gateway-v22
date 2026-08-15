from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
INSTALL=(ROOT/'install.sh').read_text(encoding='utf-8')
MANIFEST=(ROOT/'release-manifest.json').read_text(encoding='utf-8')


def test_015_is_full_ui_not_overlay():
    assert (ROOT/'app/main.py').is_file()
    assert (ROOT/'app/web/templates/clients.html').is_file()
    assert (ROOT/'app/web/templates/routing.html').is_file()
    assert (ROOT/'app/web/templates/maintenance.html').is_file()
    assert 'detect_minimal_013_install' in INSTALL
    assert 'restore_minimal_013_clients' in INSTALL


def test_015_preserves_confirmed_013_xray_values():
    for marker in (
        'MIGRATION_XRAY_PRIVATE',
        'MIGRATION_XRAY_PUBLIC',
        'MIGRATION_XRAY_SHORT_ID',
        'MIGRATION_VLESS_ENCRYPTION',
        'MIGRATION_VLESS_DECRYPTION',
        'vless_auth="mlkem768"',
    ):
        assert marker in INSTALL
    assert 'DEFAULT_PANEL_PORT="63443"' in INSTALL
    assert 'xray mlkem768' in INSTALL
    assert 'xray run -test -config' in INSTALL


def test_015_uses_sg_panel_vless_contract():
    contract=(ROOT/'app/xray/sg_panel_vless.py').read_text(encoding='utf-8')
    assert '"dest"' in contract
    assert '"network": "tcp"' in contract
    assert '"network": "xhttp"' in contract
    assert 'VLESSENC_SERVER_MODE_DEFAULT = "auto"' in contract
    assert 'VLESSENC_CLIENT_MODE_DEFAULT = "stream-one"' in contract
    assert 'REALITY_TCP_FLOW = "xtls-rprx-vision"' in contract


def test_015_does_not_create_client_during_013_migration():
    assert 'CREATE_SG_ADMIN="0"' in INSTALL
    assert 'MIGRATE_MINIMAL_013=1' in INSTALL
    assert 'seed_update_mode="0"' in INSTALL
    assert '"automatic_client_creation": false' in MANIFEST
    assert 'SG_GATEWAY_ADMIN_PASSWORD_HASH' in INSTALL
    assert 'Логин и пароль SG-Gateway 013 сохраняются' in INSTALL
